# Wx-Usis

This Python software aims in driving an USIS-compliant spectroscope. So far, only the UVEX supports this protocol, so it has only been tested against this model.
It relies on the WX graphics library ( https://wxpython.org/ ), which provides a cross-platform GUI toolkit.

## Supported OS and Python

| OS            | Python                      | Notes                                                                                      |
| ------------- | -------------               | ---------                                                                                  |
| Windows 10    | 3.7 (Anaconda environment)  | Should work on Windows 11, as Anaconda isolates the Python code from the OS inner layers. |
| Linux         | 3.7                         | Tested on Debian 11 and Ubuntu 20.04, but should work on Fedora/RedHat flavors as well.     |

## Installation

It is highly recommended to run this code into a Python virtual environment, either with anaconda/miniconda (https://anaconda.org/) or with the Python virtualenv toolkitfs.
Then install the **wxpython** and the **pyserial** packages. This is it.

## Notes
Some more recent Python version (3.8+) should also work as long as the wxpython package exists for this version. As of today, this is not the case for some Linux-based environments.



