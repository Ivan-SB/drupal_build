This script automate:
* downloading Drupal
* setting up the database (MySQL or PostgreSQL)
* installing local Drush in Drupal directory
* installing Drupal via Drush
* install modules and themes
* enable modules and themes
* set default and admin theme
* install drupal-check

It can simply download and unpack modules in the right place.

It can also automate wiping a drupal installation, deleting files, database user and database.

It can use a cache to avoid downloading over and over the same files.

It can install modules and themes by varous means (unpack archives, composer, git clone) 

It uses a yaml configuration file whose entries can be overwritten by command line paramethers

It automatically chose the latest available release (stable or dev) for the specified version of Drupal

It support an "internal" repo

drush theme:uninstall stark return an error even if theme is correctly uninstalled but prevent script to terminate correctly.
