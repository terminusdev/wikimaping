Convert photo collection for uploading to wikimapia.org:
 - Downscale to ~ 1920 x 1440
   (wikimapia itself reduces the resolution of photos to ~ 960 x 720)
 - Compress (wikimapia can't upload file greater than ~ 2 Mb)
 - Remove EXIF data (anyway wikimapia drops EXIF)
 - Add text label (date, file name, etc.)

ImageMagick required.
http://www.imagemagick.org
https://imagemagick.org/download/binaries/
Tested versions:
  ImageMagick 6.8.8-8 Q16 x86 2014-03-07
  https://ftp.icm.edu.pl/packages/ImageMagick/binaries/ImageMagick-6.8.8-8-Q16-x86-windows.zip
  ImageMagick 6.9.11-27 portable Q16 x64
  https://imagemagick.org/download/binaries/ImageMagick-6.9.11-27-portable-Q8-x64.zip
  ImageMagick 7.0.10-27 (converts about 4x slower - Q16 or Q8, x86 or x64,
                         with or without HDRI, with or without OpenMP
                         (multithreading support) - no matter)
  https://imagemagick.org/download/binaries/ImageMagick-7.0.10-27-portable-Q16-x64.zip

Tested on Python 3.4, 3.8

------------------------------------------------------------------------------

Define path to the ImageMagick utilities in wikimaping.py, for example:

For new ImageMagick versions (>= 7.0):
IM_CONVERT = ["C:\\Program Files\\ImageMagick\\magick.exe", "convert"]
IM_IDENTIFY = ["C:\\Program Files\\ImageMagick\\magick.exe", "identify"]

For old ImageMagick versions (< 7.0):
IM_CONVERT = ["C:\\Program Files\\ImageMagick\\convert.exe"]
IM_IDENTIFY = ["C:\\Program Files\\ImageMagick\\identify.exe"]

------------------------------------------------------------------------------

ATTENTION!
You have to allow reading the "@*" path pattern in the ImageMagick policy
(/etc/ImageMagick-*/policy.xml)
in order to add multi-line or non-ascii labels to an image:
  <policy domain="path" rights="read" pattern="@*"/>

------------------------------------------------------------------------------

usage: wikimaping.py [--destination=<folder>] [--nobackup] [--label=<template>] [--label_alignment=<corner>] <source dir> | <source file>...

positional arguments:
  path                  Paths to files and/or folders for processing.

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  -d TARGET, --destination TARGET
                        Destination folder
                        (if not defined, the files will be
                        converted in the original folder)
  -n, --nobackup        Don't keep original photo when converting in place
                        (--destination folder not defined)
  -l LABEL, --label LABEL
                        Add a text label to the photo according to the template.
                        This is any text and TAGS in square brackets.
                        Examples for photo file HAPPY_SHOT.JPG was taken on
                        August 20, 2020 at 16:33:53 (according to EXIF):
                         any text                   -> any text
                         [YYYY-MM-DD hh:mm:ss]      -> 2020-08-20 16:33:53
                         [file_name]                -> HAPPY_SHOT
                         [Month YYYY, ][file_name]  -> August 2020, HAPPY_SHOT
                         [MONTH YYYY, ](C) Author   -> AUGUST 2020, (C) Author
                         [month DD, YYYY. ]Any text -> august 20, 2020. Any text
                         [[square brackets]]        -> [square brackets]
  -a {TopLeft,TopRight,BottomLeft,BottomRight}, --label_alignment {TopLeft,TopRight,BottomLeft,BottomRight}
                        Place the label in one of the image corners.

Examples:
wikimaping.py image.jpg
wikimaping.py image.jpg --nobackup
wikimaping.py image.jpg --destination "Photos/To Wikimapia"
wikimaping.py "Photos/Some file.jpg" "Photos/Some folder" --destination "Photos/Temp"
wikimaping.py image.jpg --label "[YYYY]"
wikimaping.py image.jpg --label "[YYYY-MM-DD hh:mm:ss]" --label_alignment BottomLeft
wikimaping.py image.jpg --label "[YYYY-MM-DD ]Image description"
wikimaping.py place1.jpg place2.jpg --label "[Month YYYY, ][file_name]"
wikimaping.py "Photos/Central park" --label "Central park"
