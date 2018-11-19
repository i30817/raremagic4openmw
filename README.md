# raremagic
A python script inspired from omwllf metaprogramming to create two morrowind mods: learnable scrolls and no spells for sale

Currently it creates two omwaddons: no\_spells\_for\_sale and scribe\_scrolls.

no\_spells\_for\_sale works like the plugin of the same name for MWSE and disables the spell buying menu, but without requiring MWSE.

It also removes some, but not all of the spell scrolls in vendor inventories.

scribe\_scrolls allows you to drop scrolls into your character paperdoll and learn them if you have the relevant stat at a high enough level.

The intent of the mod is to make looting scrolls a bit more important, much like ultima 7 way back when (although ultima 7 still has a much better spellbook).

## How to use this

First, make sure you have python (version 3.5 or higher) installed on your system and reachable.

Second, make sure the script itself (`raremagic.py`) is downloaded and available. You can download it from github at https://github.com/i30817/raremagic4openmw

Then, [install your mods in the OpenMW way](https://wiki.openmw.org/index.php?title=Mod_installation), adding `data` lines to your `openmw.cfg`.

Make sure to start the launcher and enable all the appropriate `.esm`, `.esp`, and `.omwaddon` files. Drag them around to the appropriate load order.

Then, run `raremagic.py` from a command line (Terminal in OS X, Command Prompt in Windows, etc). This should create two new `.omwaddon` modules.

Open the Launcher, drag the new modules to the bottom (they should be loaded near last, and won't interfere with owmllf), and enable them.

Finally, start OpenMW.

