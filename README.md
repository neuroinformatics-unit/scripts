# Scripts
Small but useful scripts to share among users.

## Bash scripts
### Instructions for macOS / Linux users
To run a bash script, you need to have bash installed on your system. It should be already installed on Linux and macOS.
You can check if you have bash installed by running the following command in your terminal:
```bash
$ bash --version
```
In case it is not installed, on Linux install bash with the following command:
```bash
$ sudo apt-get install bash
```
and on macOS:
```bash
$ brew install bash
```
To run a bash script, you need to make it executable by running the following command in your terminal:
```bash
$ chmod +x script.sh
```
Then, you can run the script by running the following command in your terminal:
```bash
$ ./script.sh
```
In case you want to add the script to your PATH, you can run the following command in your terminal:
```bash
$ sudo cp script.sh /usr/local/bin/script
```
Then, you can run the script by running the following command in your terminal:
```bash
$ script
```
It would run on macOS even if the shell is in `zsh`.
