# MaaazeRunner

MaaazeRunner is a graphical adventure and known-answer builder for the Bay Park
Ollama Console project. It can add and edit rooms, items, puzzles, and
prepopulated Decision Tree answers; import and export complete repair bundles;
validate generated data; and publish approved generated files to GitHub on a
schedule. Scheduled runs automatically pull the latest main branch, validate the generated output, commit approved changes, and push them to GitHub.

The built-in world also includes The Reflect Room, which records lessons learned from the app-development and recovery exercise.

For safety, MaaazeRunner does not modify or stage `app.py`. An automatic guard
checks the protected `app.py` checksum and restores the verified copy if another
T14 script changes it.

Created July 20, 2026 by Jeremiah O'Neal.

For more information, visit https://j03.page/

## License

This program is free software licensed under the GNU General Public License,
version 3 (GPLv3). You may redistribute and modify it under the terms of GPLv3.
