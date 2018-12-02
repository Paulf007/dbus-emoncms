# dbus-emoncms
A Python Script to upload Victron data to Emoncms directly from Venus OS / Color control 

You will need to give root access to your CCGX / Color control to be able to run the script. 
More information can be found here :
https://www.victronenergy.com/live/ccgx:root_access

Instalation 

Once you have access to Venus OS navigate to the /data folder and upload the dbus-emoncms.py to the root of the folder.
Navigate to the data folder and edit the script with your emoncms server details. 

To run the script from terminal : 
Navigate to data folder 
 cd / data
Run the Script  
 python dbus-emoncms.py
 
To run from boot: 
First make the file executable
cd / data 
chmod +x dbus-emoncms.py
Add rc.local file to the root of your /data file 
Add the following to the rc.local file :


sleep 120

nohup /usr/bin/python /data/dbus-emoncms.py & >/data/emoncms_output.log &

exit 0

You need the sleep command as it takes the d-bus a few seconds to start up. 

You should see the data coming through to emoncms after about 3 minutes.

