# Sub Rosa SBL Tool
<img width="430" height="400" alt="image" src="https://github.com/user-attachments/assets/1b8b01ba-1382-466f-b1d3-39c611a56880" />


This is a Blender plugin that allows you to port objects from Blender into Sub Rosa by turning them into the .sbl file format, below I'll outline the basic steps to go from how to play your map on version v24 to the latest release (v38):

## Export your object from Blender 
First install the Blender plugin then create your object, I won't go into texture baking but if you want to have several textures on one object you'll require it, I'll link resources I found helpful at the bottom of this guide. After you've finished, highlight the object(s) you want to turn into an sbl file and hit **File > Export > .sbl**

## Install Sub Rosa v24
Next step is to install the v24 of Sub Rosa, here's a link to an archive I found but there are others: [https://crypticsea.gart.sh/](https://crypticsea.gart.sh/Sub%20Rosa/0.24/)

(NOTE: This guide is pretty rough so if I get any details wrong like whether it's the b or c folder I'd recommend checking out this video by Cucremus it will give you a lot of necessary context so you have a better idea about wtf I'm talking about if you're new to this https://youtu.be/352DVmywYzY remember the tools shown in that video are different than the ones here though)

## Setup map editor
Once you've got the right outdated version installed download Cheat Engine and load city_editor1.CT and once it's attached to Sub Rosa (v24), change the editor enabled value from 0 to 1 from here get familiar with the editor, notable things that might seem strange is you can only delete or place cubes on a big grid that you summon with T, actually I'll just drop the guide as a .txt idk who wrote it I think it was RappapaThePepper or Gamemaster777

Anyway, take your exported .sbl and drop it into your game file /block folder **THIS IS ALSO IMPORTANT** I would heavily recommend naming your .sbl after an existing .sbl and replacing it this is to do with another file format called .sbb and unless you want to get into hex editing you'll find this a lot easier, my recommendation is one of the signs of the bases like bc-sign-goldmen.sbl
<img width="238" height="87" alt="image" src="https://github.com/user-attachments/assets/2ff474c3-0de1-41ba-b204-9db196f52911" />

## Updating to latest version
Once you've saved and reloaded your map from following the other guide (just press f9 and f5) you'll be able to play with your custom buildings, the problem is nobody plays on v24 except Brazilians and that is only sometimes, so you'll want to port your map to the latest version, v38, to do this you can build this csx tool on your machine as the link doesn't seem to work anymore:
https://github.com/jpxs-intl/CSXWebParser 

Basically your aim is to turn all your files into a .csx you do this by dragging all files inside your block, buildblock, and texture folders into the parser and hitting download, once you finally have your .csx go to wherever your game files of v38 are, hit data, if you want to test your map out in practice mode (which means you don't need a server) call it 'test2', otherwise call it whatever you want, then make sure it looks something like this <img width="664" height="161" alt="image" src="https://github.com/user-attachments/assets/dfb7242d-3392-4ef0-ad00-ec2b0205e309" /> if you're missing files you can take them from other maps you already have eg. buildblock

Now if you load up the game you should hopefully be greeted with your custom buildings in game, whilst you can truly make anything you want you'll soon find there are limits to what the game is able to handle, I encourage you to find these for yourself and know there are workarounds, for instance to get over the vertex limit you can stitch several .sbl files together, I have that tool as well but I won't be releasing it as I wasn't involved with its creation also it's kind of doodoo water

## Credits / Notes
I finished this project around February 2026 and used OpenAI's o3 model to help me understand decompiled functions and write parts of the code.

If you have any problems or questions, or if you make something cool, you can contact me **@Adyox0** on Discord

https://youtu.be/SDqpnfTRtIU

https://youtu.be/No2i3O1yozo

<img width="1920" height="1080" alt="209A14~1" src="https://github.com/user-attachments/assets/97f81fa1-b18b-4f80-802e-012d23386564" />
<img width="1920" height="1080" alt="209C5F~1" src="https://github.com/user-attachments/assets/e9b83e53-5b53-4bf0-a375-2046423fe163" />
<img width="1920" height="1080" alt="206BEC~1" src="https://github.com/user-attachments/assets/216af149-92c3-457f-9e82-5c5b38a91c6c" />

