# HAUI

HAUI is a Home Automation User Interface initially designed for Home assistant community but suitable for any home automation system. It's based on a 7in capacitive touch display and a Raspberry Pi using a modified version of FullPageOS kiosk OS.

<img src="https://haui.remorh.com/haui-07/marketing_002.jpg" alt="HAUI_01" style="width:300px;"/>

Find more information about [HAUI here]([url](https://haui.remorh.com/haui-07/)).

# This Repo: HAUI Controls and Wizard

This repository contains the two pages of the Home Assistant User Interface to support the setup wizard (/haui-wizard) and adjustments after installed (/controls).

At the first boot the HAUI is set to open automatically the /haui-wizard page to suppor the user on setting up the device. At the first boot, the first configuration required is the WiFi. Once WiFi is ready, you can access your HAUI from any other computer's browser on the same network.

Both pages can be assessed via http://[your ip or hostname]/haui-wizard or http://[your ip or hostname]/controls after the installation is completed.

## Location of the files

The files are served on /var/www/html which is the location for the internal webpages for HAUI by lightttp on the Front Page OS System.

## Files content

### /api/app.py

The services are executed with "flask". The file app.py contains the interfaces with the system to be acessed via /api/[command]
Example: /api/reboot will execute a reboot of the HAUI.

### /controls/index.html

The html file that is shown once you access http://[your ip or hostname]/controls. 

### /haui-wizard

The html file that is shown once you access http://[your ip or hostname]/haui-wizard
