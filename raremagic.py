#!/usr/bin/env python3

from struct import pack, unpack
from datetime import date
from pathlib import Path
import os.path
import argparse
import sys
import re
from typing import List
import random

configFilename = 'openmw.cfg'
configPaths = { 'linux':   '~/.config/openmw',
                'freebsd': '~/.config/openmw',
                'darwin':  '~/Library/Preferences/openmw' }

modPaths = { 'linux':   '~/.local/share/openmw/data',
             'freebsd': '~/.local/share/openmw/data',
             'darwin':  '~/Library/Application Support/openmw/data' }


def spellname_from_scroll(name, fname):
    #some 'normal' spells with only one effect with non-standard names, which might be changed by patches
    if name == 'sc_messengerscroll':
        return 'Scribed Summon Scamp'
    elif name == 'sc_summondaedroth_hto':
        return 'Scribed Summon Daedroth'
    elif name == 'sc_radrenesspellbreaker':
        return 'Scribed Radrene\'s Spell Breaker'
    elif name == 'sc_recall': 
    #this is not the 'recall' scroll that appears in game, but may as well fix the case here
        return 'Scribed Recall'
    elif fname.startswith('Scroll of The '): #some
        return 'Scribed ' + fname[len('Scroll of The '):]
    elif fname.startswith('Scroll of the '): #some
        return 'Scribed ' + fname[len('Scroll of the '):]
    elif fname.startswith('Scroll of '): #many
        return 'Scribed ' + fname[len('Scroll of '):]
    elif fname.startswith(('L1', 'L2', 'L3', 'L4', 'L5')): #many in uvirith's legacy
        return 'Scribed ' + fname[0:3] + fname[13:] #removed 'Scroll of '
    else: #fallback, might look weird but hopefully never happens
        return 'Scribed '+ fname

class Magic:
    def __init__(self, cost, dur_mult, color, name, effect_table):
        self.cost = cost
        self.dur_mult = dur_mult
        self.color = color
        self.name = name
        self.effect_table = effect_table

    def updatecost(self, duration, min_mag, max_mag):
        if duration <= 1: #instant, probably on self, deserves bump
            duration = 40
        #introduce randomness, even if the cost of series of spells don't make sense
        mag = (min_mag + max_mag) / 2 + self.dur_mult*duration
        mag = max(0, min(100, mag))
        if mag > self.cost:
            if mag <= 10:
                mag += random.randint(0, 10)
            elif mag >= 90:
                mag += random.randint(-10, 0)
            else:
                mag += random.randint(-4, 4)
            self.cost = int(mag)

class Schools:
    #effect number tables come from https://en.uesp.net/morrow/hints/mweffects.shtml
    def __init__(self):
        self.Alteration = Magic(0, 0.15, '5A2458', 'Alteration', [0,1,2,3,4,5,6,7,8,9,10,11,12,13])
        self.Conjuration = Magic(0, 0.25, '642D00', 'Conjuration', [101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,118,119,120,121,122,123,124,125,126,127,128,129,130,131,134])
        self.Destruction = Magic(0, 0.08, '9B0000', 'Destruction', [14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,132,133,135,136])
        self.Illusion = Magic(0, 0.2, '113D25', 'Illusion', [39,40,41,42,43,44,45,46,47,48,49,50,51,52,54,55,56])
        self.Mysticism = Magic(0, 0.2, '383C9C', 'Mysticism', [53,57,58,59,60,61,62,63,64,65,66,67,68,85,86,87,88,89])
        self.Restoration = Magic(0, 0.2 , '001BB9', 'Restoration', [69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,90,91,92,93,94,95,96,97,98,99,100,117])

def createScript(script_name: str, spell_record_name: str, spell_name: str, schools: List[Magic]):
    if_block = ''
    endif_block = ''
    for magic_school in schools:
        if magic_school.cost > 0:
            if_block += '\n        if (player->Get{} >= {})'.format(magic_school.name,magic_school.cost)
            endif_block += '\n        endif'
    return \
'''begin {}
short OnPCEquip
short PCSkipEquip
if (MenuMode == 0)
    return
endif
if (OnPCEquip == 1)
    set OnPCEquip to 0
    if (player->GetSpell "{}" == 0){}
            player->AddSpell "{}"
            messagebox "You have learned the spell '{}'!"
            playsound "skillraise"
            return{}
        set PCSkipEquip to 0
        messagebox "More study is required to scribe this scroll."
    else
        set PCSkipEquip to 0
    endif
    return
endif
set PCSkipEquip to 1
end {}
'''.format(script_name, spell_record_name, if_block, spell_record_name, spell_name, endif_block, script_name)

def packLong(i):
    # little-endian, "standard" 4-bytes (old 32-bit systems)
    return pack('<l', i)

def packPaddedString(s, l):
    bs = bytes(s, 'ascii')
    if len(bs) > l:
        # still need to null-terminate
        return bs[:(l-1)] + bytes(1)
    else:
        return bs + bytes(l - len(bs))

def parseString(ba):
    i = ba.find(0)
    return ba[:i].decode(encoding='ascii', errors='ignore')

def parseNum(ba):
    return int.from_bytes(ba, 'little')

def parseFloat(ba):
    return unpack('f', ba)[0]

def readHeader(ba):
    header = {}
    header['type'] = ba[0:4].decode()
    header['length'] = int.from_bytes(ba[4:8], 'little')
    return header

def readSubRecord(ba):
    sr = {}
    sr['type'] = ba[0:4].decode()
    sr['length'] = int.from_bytes(ba[4:8], 'little')
    endbyte = 8 + sr['length']
    sr['data'] = ba[8:endbyte]
    return (sr, ba[endbyte:])

def readRecords(filename):
    fh = open(filename, 'rb')
    while True:
        headerba = fh.read(16)
        if headerba is None or len(headerba) < 16:
            return None

        record = {}
        header = readHeader(headerba)
        record['type'] = header['type']
        record['length'] = header['length']
        record['subrecords'] = []
        # stash the filename here (a bit hacky, but useful)
        record['fullpath'] = filename

        remains = fh.read(header['length'])

        while len(remains) > 0:
            (subrecord, restofbytes) = readSubRecord(remains)
            record['subrecords'].append(subrecord)
            remains = restofbytes

        yield record

def getRecords(filename, rectypes):
    numtypes = len(rectypes)
    retval = [ [] for x in range(numtypes) ]
    for r in readRecords(filename):
        if r['type'] in rectypes:
            for i in range(numtypes):
                if r['type'] == rectypes[i]:
                    retval[i].append(r)
    return retval

def readCfg(cfg):
    # first, open the file and pull all 'data' and 'content' lines, in order

    data_dirs = []
    mods = []
    with open(cfg, 'r') as f:
        for l in f.readlines():
            # match of form "blah=blahblah"
            m = re.search(r'^(.*)=(.*)$', l)
            if m:
                varname = m.group(1).strip()
                # get rid of not only whitespace, but also surrounding quotes
                varvalue = m.group(2).strip().strip('\'"')
                if varname == 'data':
                    data_dirs.append(varvalue)
                elif varname == 'content':
                    mods.append(varvalue)

    # we've got the basenames of the mods, but not the full paths
    # and we have to search through the data_dirs to find them
    fp_mods = []
    for m in mods:
        for p in data_dirs:
            full_path = os.path.join(p, m)
            if os.path.exists(full_path):
                fp_mods.append(full_path)
                break

    print("Config file parsed...")

    return fp_mods

def toSigned32(n):
    n = n & 0xffffffff
    return (n ^ 0x80000000) - 0x80000000

def partition(items, predicate=bool):
    '''first tuple list if predicate true, second if false'''
    import itertools
    a, b = itertools.tee((predicate(item), item) for item in items)
    return ((item for pred, item in b if pred), (item for pred, item in a if not pred))

def packTES3(author, desc, numrecs):
    # 1rst float version, 2nd long filetype
    head = pack('<f', 1.0) + bytes(4) + packPaddedString(author, 32) + packPaddedString(desc, 256) + packLong(numrecs)
    #we do not want masters for this mod, since it doesn't matter, only that you regenerate.
    d = { 'type':'TES3', 'HEDR':head, 'MAST':'Morrowind.esm', 'DATA': b'u9\xc2\x04\x00\x00\x00\x00' }
    return packRecord(d)

def packSpell(enchantment, spell_recname, spell_name, cost):
    spdt_bs = packLong(0) + packLong(cost) + packLong(0)
    sub_enchants = enchantment.get('ENAM')
    d = { 'type':'SPEL', 'NAME':spell_recname, 'FNAM':spell_name,'SPDT':spdt_bs, 'ENAM':sub_enchants }
    return packRecord(d)

def packScript(name, text):
    #52 is the length of this subrecord
    #name padded to 32
    #openmw doesn't use SCVR, but SCDT still 'exists' as a zero size field
    extended = packPaddedString(name, 32) +\
                packLong(0) + packLong(0) + packLong(0) +\
                packLong(0) + packLong(0)

    d = { 'type':'SCPT', 'SCHD':extended, 'SCDT':bytes(0), 'SCTX':bytes(text, 'ascii') }
    return packRecord(d)

# 'generic' pack record method.
def packRecord(rec):
    def serialize(t,k,v):
        l = len(v)
        if isinstance(v, str):
            #strangely TEXT in books doesn't have a terminating \0 (didn't check potions)
            #do this to be easier to verify in vbindiff, even if it's unlikely to cause errors
            if k == 'TEXT' and t == 'BOOK':
                return bytes(k, 'ascii') + packLong(l) + bytes(v,'ascii')
            return bytes(k, 'ascii') + packLong(l+1) + bytes(v,'ascii') + bytes(1)
        else:
            return bytes(k, 'ascii') + packLong(l) + v #is bytes if not str

    reclen = 0
    recbyt = b''
    t  = rec.pop('type')
    for k,c in rec.items():
        if isinstance(c, tuple):
            for v in c:
                b = serialize(t, k, v)
                reclen += len(b)
                recbyt += b
        else:
            b = serialize(t, k, c)
            reclen += len(b)
            recbyt += b
    return bytes(t, 'ascii') + packLong(reclen) + bytes(8) + recbyt
#'generic' parse record method. stores (string, value) or (string, (values...))

# uses a whitelist to recognize which fields should be part of a tuple
# uses a blacklist to recognize subrecords that should not be turned into strings
# remember to analise the record on https://en.uesp.net/morrow/tech/mw_esm.txt
# to figure out if what subrecords to add to the blacklist and whitelist
def parseRecord(rec, binary_blacklist, multi_whitelist = []):
    d  = {'type' : rec['type'] } #always string
    sr = rec['subrecords']

    for r in sr:
        r_id = r['type']
        r_va = r['data']
        if r_id not in binary_blacklist:
            r_va = parseString(r_va)
        if r_id in multi_whitelist:
            d[r_id] = d.get(r_id, tuple()) + (r_va,)
        else:
            d[r_id] = r_va
    return d

def main(cfg, outmoddir):
    fp_mods = readCfg(cfg)

    mod1Name = 'scribe_scrolls.omwaddon'
    mod2Name = 'no_spells_for_sale.omwaddon'
    mod1 = os.path.join(baseModDir, mod1Name)
    mod2 = os.path.join(baseModDir, mod2Name)

    #these subrecords can't be stored as strings
    binary_blacklist = ['BKDT', 'DELE', 'ENDT', 'NPDT', 'FLAG', 'NPCO', 'NPCS', 'AIDT', 'AI_W', 'AI_T', 'AI_F', 'AI_E', 'AI_A', 'DODT', 'XSCL']

    # unlike a levelled list merge, we only want the 'latest' version of records.
    rbook, rench, rnpcs = [], [], []
    for f in fp_mods:
        base = os.path.basename(f)
        #filter out 'our own' files.
        if base == mod1Name or base == mod2Name:
            continue

        (rbookt, encht, npct) = getRecords(f, ('BOOK', 'ENCH', 'NPC_'))
        rnpcs += [ parseRecord(x, binary_blacklist, ['NPCO', 'NPCS']    ) for x in npct   ]
        rbook += [ parseRecord(x, binary_blacklist                      ) for x in rbookt ]
        #ENAM is a duplicated ID (also in books) and only binary this time
        rench += [ parseRecord(x, binary_blacklist + ['ENAM'], ['ENAM'] ) for x in encht  ]
    
    #dedup, last have priority and 'win', name is the id for books, enchantments and npcs 
    from collections import OrderedDict
    rbook = OrderedDict( (rec['NAME'], rec) for rec in rbook ).values()
    rench = OrderedDict( (rec['NAME'], rec) for rec in rench ).values()
    rnpcs = OrderedDict( (rec['NAME'], rec) for rec in rnpcs ).values()

    def is_magic_scroll(x):
        return 'DELE' not in x and 'ENAM' in x and int(x['BKDT'][8]) == 1
    def has_script(x):
        return 'SCRI' in x
    def magic_scroll_cost(enchantment):
        #some scrolls have screwed up 'costs' like 'supreme domination', 'windform'
        #The max spell cost in morrowind is about 180 and in Tamriel Rebuilt 200, so let's limit it
        cost = parseNum(enchantment['ENDT'][4:8])
        return cost if cost <= 190 else 200 - random.randint(0,20)

    #we don't want to modify magic scrolls already with a script... 
    #except for their text to indicate it can't be learned in-game because of 'strange magic'
    scripts, scrolls, spells = [], [], []
    scripted_magic_scrolls, magic_scrolls = partition(filter(is_magic_scroll, rbook), has_script)
    magic_scrolls = list(magic_scrolls)    

    for x in scripted_magic_scrolls:
        x['TEXT'] += '<FONT><DIV ALIGN="LEFT"><BR><BR>This scroll strange magic is impossible to learn<BR><BR></FONT>'
        scrolls += [packRecord(x)]

    for x in magic_scrolls:
        enchantment = next( e for e in rench if x['ENAM'] == e['NAME'] and 'DELE' not in e )
        if not enchantment:
            x['TEXT'] += '<FONT><DIV ALIGN="LEFT"><BR><BR>This scroll strange magic is impossible to learn<BR><BR></FONT>'
            scrolls += [packRecord(x)]
            continue

        #black magic for getting attributes from a newly instanciated object because enums are singletons
        schools = [e for e in Schools().__dict__.values()]
        #for each school only count the highest difficulty enchantment component
        for effect in enchantment['ENAM']:
            for magic_school in schools:
                effect_id = parseNum(effect[0:2])
                if effect_id in magic_school.effect_table:
                    magic_school.updatecost(parseNum(effect[12:16]), parseNum(effect[16:20]), parseNum(effect[20:]))
                    break

        script_name = 'lrn_' + x['NAME']
        script_name = script_name[:32] #maybe truncate, if needed (32 bytes is the max size)
        x['SCRI'] = script_name

        x['TEXT'] += '<FONT><DIV ALIGN="LEFT"><BR><BR>Learning from this scroll requires these skills<BR><BR></FONT>'
        for mag_school in schools:
            color,cost,name = mag_school.color,mag_school.cost,mag_school.name
            if cost > 0:
                x['TEXT'] += '<FONT COLOR="{}"><DIV ALIGN="LEFT">{} {}<BR></FONT>'.format(color,cost,name)

        spell_name = spellname_from_scroll(x['NAME'], x['FNAM'])
        spell_record_name  = 'spl_' + x['NAME']
        scripts += [packScript(script_name, createScript(script_name, spell_record_name, spell_name, schools))]
        scrolls += [packRecord(x)]
        spells  += [packSpell(enchantment, spell_record_name, spell_name, magic_scroll_cost(enchantment))]

    def clearBit(int_type, offset):
        mask = ~(1 << offset)
        return(int_type & mask)
    def testBit(int_type, offset):
        mask = 1 << offset
        return(int_type & mask)

    npcs = []
    vendors = []
    magic_scroll_names = [ x['NAME'] for x in magic_scrolls ]
    magic_scroll_names.append('random_scroll_all')
    for npc in rnpcs:
        if 'AIDT' not in npc and 'DELE' not in npc:
            continue

        add = False
        flags = parseNum(npc['AIDT'][8:])
        
        #spell seller
        if testBit(flags,11):
            #print(npc['NAME'])
            new_flag = clearBit(flags,11)
            npc['AIDT']=npc['AIDT'][0:8]+packLong(new_flag,)
            add = True

        #magic_items, misc_item or book_items sellers or potions
        can_sell_scrolls = testBit(flags, 10) or testBit(flags,12) or testBit(flags,3) or testBit(flags,13)
        if can_sell_scrolls and 'NPCO' in npc:
            items = npc['NPCO']
            items_without_scrolls = [ item for item in items if parseString(item[4:]) not in magic_scroll_names ]
            if len(items) > 0 and len(items) != len(items_without_scrolls):
                npc['NPCO'] = tuple(items_without_scrolls)
                add = True

        #still missing the items on the store cell, but we'll see
        if add:
            npcs.append(packRecord(npc))

    author  = "i30817, copyright 2018"
    moddesc = "scribe scrolls: scrolls from all mods (at the time of creation) can be learned. Scrolls with a magicka cost above 200 will have their cost randomized between 180-200. Requires to be near the end of the load order."
    if not os.path.exists(outmoddir):
        p = Path(outmoddir)
        p.mkdir(parents=True)

    with open(mod1, 'wb') as f:
        f.write(packTES3(author, moddesc, len(scripts)+len(scrolls)+len(spells)))
        for script in scripts:
            f.write(script)
        for spell in spells:
            f.write(spell)
        for scroll in scrolls:
            f.write(scroll)

    moddesc = "no spells for sale: prevents all npcs from all mods (at the time of creation) from selling spells or spell scrolls in their inventory - due to a engine pecularity they will still sell scrolls if at their localization (on containers or in the world)."
    with open(mod2, 'wb') as f:
        f.write(packTES3(author, moddesc, len(npcs)))
        for npc in npcs:
            f.write(npc)
    
    print("\n\n****************************************")
    print(" When you next start the OpenMW Launcher, look for 2 modules named '{}' and '{}'.".format(mod1Name,mod2Name))
    print(" Drag them to the bottom of the load list and enable one or both them.\n They need to load after all modules that add scrolls or npcs.\n Can be at the very last or just before the omwllf plugin.")
    print()
    print(" Do not share the created files - these omwaddons are created based on your current load list and shouldn't be shared.")
    print(" Do not move the created files to the morrowind Data Files dir, since this would create confusing duplicates on the load list.")
    print(" Do not rename the created omwaddons when creating your list - this program uses that filename to filters old versions to avoid order problems between the two modules, otherwise '{}' would have to load before '{}' - but only if both were used and only the second time you created them, which is confusing".format(mod2Name,mod1Name))
    print("\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-c', '--conffile', type = str, default = None,
                        action = 'store', required = False,
                        help = 'Conf file to use. Optional. By default, attempts to use the default conf file location.')

    parser.add_argument('-d', '--moddir', type = str, default = None,
                        action = 'store', required = False,
                        help = 'Directory to store the new module in. By default, attempts to use the default work directory for OpenMW-CS')
    p = parser.parse_args()


    # determine the conf file to use
    confFile = ''
    if p.conffile:
        confFile = p.conffile
    else:
        pl = sys.platform
        if pl in configPaths:
            baseDir = os.path.expanduser(configPaths[pl])
            confFile = os.path.join(baseDir, configFilename)
        elif pl == 'win32':
            # this is ugly. first, imports that only work properly on windows
            from ctypes import *
            import ctypes.wintypes

            buf = create_unicode_buffer(ctypes.wintypes.MAX_PATH)

            # opaque arguments. they are, roughly, for our purposes:
            #   - an indicator of folder owner (0 == current user)
            #   - an id for the type of folder (5 == 'My Documents')
            #   - an indicator for user to call from (0 same as above)
            #   - a bunch of flags for different things
            #     (if you want, for example, to get the default path
            #      instead of the actual path, or whatnot)
            #     0 == current stuff
            #   - the variable to hold the return value

            windll.shell32.SHGetFolderPathW(0, 5, 0, 0, buf)

            # pull out the return value and construct the rest
            baseDir = os.path.join(buf.value, 'My Games', 'OpenMW')
            confFile = os.path.join(baseDir, configFilename)
        else:
            print("Sorry, I don't recognize the platform '%s'. You can try specifying the conf file using the '-c' flag." % p)
            sys.exit(1)

    baseModDir = ''
    if p.moddir:
        baseModDir = p.moddir
    else:
        pl = sys.platform
        if pl in configPaths:
            baseModDir = os.path.expanduser(modPaths[pl])
        elif pl == 'win32':
            # this is ugly in exactly the same ways as above.
            # see there for more information

            from ctypes import *
            import ctypes.wintypes

            buf = create_unicode_buffer(ctypes.wintypes.MAX_PATH)

            windll.shell32.SHGetFolderPathW(0, 5, 0, 0, buf)

            baseDir = os.path.join(buf.value, 'My Games', 'OpenMW')
            baseModDir = os.path.join(baseDir, 'data')
        else:
            print("Sorry, I don't recognize the platform '%s'. You can try specifying the conf file using the '-c' flag." % p)
            sys.exit(1)


    if not os.path.exists(confFile):
        print("Sorry, the conf file '%s' doesn't seem to exist." % confFile)
        sys.exit(1)

    main(confFile, baseModDir)



