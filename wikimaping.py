"""
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
                         with or witout HDRI, with or whithot OpenMP
                         (multythreading suppot) - no matter)
  https://imagemagick.org/download/binaries/ImageMagick-7.0.10-27-portable-Q16-x64.zip

Tested on Python 3.4
"""

__version__ = "0.1.3"


import sys
import time
import re
import io
import os
import textwrap
import subprocess
import shutil
import argparse


#-Options---------------------------------------------------------------------#
# You can safely change these options in addition to the command line options
# for fine-tuning
#-----------------------------------------------------------------------------#

####REPLACE
# For new ImageMagick versions (>= 7.0):
#IM_CONVERT = "magick convert"
#IM_IDENTIFY = "magick identify"

# For old ImageMagick versions (< 7.0):
# ImageMagick convert command conflicts with the standard Windows utility
# and therefore must be renamed for example to "magick"
IM_CONVERT = "convert" if os.name != "nt" else "magick"
IM_IDENTIFY = "identify"

# You can also specify the full path to the ImageMagick utilities, for example:
#IM_CONVERT = '"C:\\Program Files\\ImageMagick\\magick.exe" convert'
#IM_IDENTIFY = '"C:\\Program Files\\ImageMagick\\magick.exe" identify'


# Files with this extensions will be converted
FILE_EXTENSIONS = ("jpg",
                   "jpeg",
                   )


# All big pictures will be downscaled to following resolution
# (wikimapia don't accept big photo)
PHOTO_MAX_SIDE = 1920
PHOTO_QUALITY = 91 # max 100% (reciprocal of compression ratio)


# Text label parameters

# Name of the font for ImageMagick (magick -list font):
#  "Roboto-Black", "Tahoma-Bold", etc
LABEL_FONT = "Arial-Black" if os.name == "nt" else "Liberation-Sans-Bold"
LABEL_FONT_SIZE = 40              # This font size corresponds
                                  # to LABEL_FONT_SIZE_PHOTO_SIDE
LABEL_FONT_SIZE_PHOTO_SIDE = 1920 # Photo resolution corresponding
                                  # to LABEL_FONT_SIZE
LABEL_COLOR = "rgb(255,255,255)"
LABEL_LINE_WIDTH = 60 # Max length of the label in characters.
                      # Longer lines will be wrapped.
                      # This value corresponds to LABEL_FONT_SIZE


MONTH_NAMES = {'01' : 'january',
               '02' : 'february',
               '03' : 'march',
               '04' : 'april',
               '05' : 'may',
               '06' : 'june',
               '07' : 'july',
               '08' : 'august',
               '09' : 'september',
               '10' : 'october',
               '11' : 'november',
               '12' : 'december'
               }


#-Constanst-------------------------------------------------------------------#

GRAPHIC_UTILITY_NAME = "ImageMagick"


"""
Photo orientation according EXIF:

  1        2       3      4         5            6           7          8

888888  888888      88  88      8888888888  88                  88  8888888888
88          88      88  88      88  88      88  88          88  88      88  88
8888      8888    8888  8888    88          8888888888  8888888888          88
88          88      88  88
88          88  888888  888888
"""

ORIENTATIONS_MAP = {'1' : 'RotateNoneFlipNone',
                    '2' : 'RotateNoneFlipHorisontal',
                    '3' : 'Rotate180FlipNone',
                    '4' : 'Rotate180FlipHorisontal',
                    '5' : 'Rotate270FlipVertical',
                    '6' : 'Rotate270FlipNone',
                    '7' : 'Rotate90FlipVertical',
                    '8' : 'Rotate90FlipNone'
                    }

ORIENTATIONS_PORTRAIT = ('RotateNoneFlipNone',
                         'RotateNoneFlipHorisontal',
                         'Rotate180FlipNone',
                         'Rotate180FlipHorisontal',
                         )

ORIENTATION_NONE = 'RotateNoneFlipNone'


# Tags that can be used in a label template
# Key - tag in template
# Value - corresponded with method in WmImageMetrics class
LABEL_TAGS = {'YYYY'      : 'year',
              'MM'        : 'month',
              'month'     : 'month_name', # august
              'MONTH'     : 'month_NAME', # AUGUST
              'Month'     : 'month_Name', # August
              'DD'        : 'day',
              'hh'        : 'hour',
              'mm'        : 'minute',
              'ss'        : 'sec',
              'file_name' : 'file_name',
              }


# Label alignment options for the four corners of the photo
ALIGNMENT_TOP_LEFT     = 'TopLeft'
ALIGNMENT_TOP_RIGHT    = 'TopRight'
ALIGNMENT_BOTTOM_LEFT  = 'BottomLeft'
ALIGNMENT_BOTTOM_RIGHT = 'BottomRight'
# Map label alignment to ImageMagick gravity
ALIGNMENT_TO_GRAVITY_MAP = {ALIGNMENT_TOP_LEFT     : 'NorthWest',
                            ALIGNMENT_TOP_RIGHT    : 'NorthEast',
                            ALIGNMENT_BOTTOM_LEFT  : 'SouthWest',
                            ALIGNMENT_BOTTOM_RIGHT : 'SouthEast'
                            }


BACKUP_DIR_NAME = "backup"


#- System utilities ----------------------------------------------------------#

def normalize_path (path):
    """Remove path separator from from the end of path."""
    dir, name = os.path.split (path)
    return path if name else dir


def path_exist (path):
    try:
        return os.path.exists (path)
    except OSError:
        pass

    return False


def path_is_dir (path):
    try:
        return os.path.isdir (path)
    except OSError:
        pass

    return False


def create_dir (dir):
    try:
        if not os.path.exists (dir):
            os.makedirs (dir)
        if not os.path.isdir (dir):
            return False
        return True
    except OSError as error:
        print (str (error))

    return False


def get_temp_file_name (dir, prefix, ext):
    res = ""
    for i in range (10):
        res = os.path.join (dir, prefix + "_94350621_TMP" + str (i) + "." + ext)
        if not path_exist (res):
            return res

    print ("ERROR! Can't create temporary file:\n  " + res + "\n")
    return ""


def get_target_path (source_root, target_root, path):
    source_root = normalize_path (source_root)
    target_root = normalize_path (target_root)
    path = normalize_path (path)

    if not path.startswith (source_root):
        return ""

    sub_path = path [len (source_root) :]
    while sub_path and (sub_path [0] == '/' or sub_path [0] == '\\'):
        sub_path = sub_path [1:]
    return os.path.join (target_root, sub_path)


def cmd_result (path, args):
    cmd = path + " " + args
    print (cmd)

    try:
        #with os.popen (cmd) as out:
        #    result = out.readlines ()
        # ....
        with subprocess.Popen (cmd, stdout=subprocess.PIPE).stdout as out:
            result = out.readlines ()
            if not result:
                return ""
    except FileNotFoundError:
        print (GRAPHIC_UTILITY_NAME +
               " not found. This path may be wrong:\n " + path)
        raise

    res = result [0].decode () # only the first line is needed
    print (res)
    return res

def cmd_exitcode (path, args):
    cmd = path + " " + args
    print (cmd)

    try:
        # os.system () has a bug on Win 7 - can't start command like this:
        # '"c:\\Folder with space\\program" -option "value in quotes"'
        res = subprocess.call (cmd)
    except FileNotFoundError:
        print (GRAPHIC_UTILITY_NAME +
               " not found. This path may be wrong:\n " + path)
        raise

    return res


#- Retrieving image parameters -----------------------------------------------#

class WmImageMetrics:
    """
    Returns various parameters of an image such as
    width, height, shooting date, etc.
    """

    def __init__ (self, path):
        self.path = path

        self.__orientation = ""

        self.__width = -1
        self.__height = -1

        self.__year = ""
        self.__month = ""
        self.__month_name = ""
        self.__month_name_error = False
        self.__day = ""
        self.__hour = ""
        self.__minute = ""
        self.__sec = ""
        self.__date_loaded = False
        self.__date_error = False

        self.__file_name = ""
        self.__file_name_error = False

    def __get_exif_date (self):
        if self.__date_error:
            return False
        if self.__date_loaded:
            return True

        self.__date_loaded = True

        # 'DateTimeOriginal'
        #     The time when the shoot was taken
        # 'DateTimeDigitized'
        #     The time when the image was digitized from analog media (film).
        #     For digital photo is the same as DateTimeOriginal
        # 'DateTime'
        #     Time when the image was last edited (modification date).
        #     It can be changed by a photo editor,
        #     often broked by MS viewer (at least old versions).
        #     BUT! Some cameras write only this tag - xiaomi for example.
        exif_date = ""
        for tag in ('DateTimeOriginal',
                    'DateTimeDigitized',
                    'DateTime'
                    ):
            im_date = ('-format "%[EXIF:' + tag + ']" ' + '"' + self.path + '"')
            exif_date = cmd_result (IM_IDENTIFY, im_date)
            if exif_date:
                break
        else:
            self.__date_error = True
            print ("ERROR! Can't get image Date and Time from EXIF!\n  " +
                   self.path + "\n")
            return False

        if tag != 'DateTimeOriginal':
            print ("ATTENTION! Can't get Original image date from EXIF!\n  " +
                   self.path + "\n" +
                   "Date maybe wrong.")

        # The date and time are returned as a string like "2020:08:19 15:47:45"
        date_time = r"\b(\d\d\d\d):(\d\d):(\d\d)\b.*\b(\d\d):(\d\d):(\d\d)\b"
        date = re.search (date_time, exif_date, flags=re.ASCII)
        if not date:
            self.__date_error = True
            print ("ERROR! Can't parse image EXIF - Date and Time!\n  " +
                   self.path + "\n")
            return False

        self.__year = date.group (1)
        self.__month = date.group (2)
        self.__day = date.group (3)

        self.__hour = date.group (4)
        self.__minute = date.group (5)
        self.__sec = date.group (6)

        return True

    def __get_width_or_height (self, get_width = True):
        param = ""
        if self.orientation () in ORIENTATIONS_PORTRAIT:
            param = "w" if get_width else "h"
        else:
            param = "h" if get_width else "w"

        im_cmd = ('-format %' + param + ' ' +
                  '"' + self.path + '"')

        im_result = cmd_result (IM_IDENTIFY, im_cmd)
        if not im_result.isdigit ():
             print ("ERROR! Can't detect image " +
                    ("width" if get_width else "height") + ":\n  " +
                    self.path + "\n")
             return 0

        return int (im_result)

    def orientation (self):
        if self.__orientation:
            return self.__orientation

        im_orientation = ('-format "%[EXIF:Orientation]" ' +
                          '"' + self.path + '"')

        exif_orientation = cmd_result (IM_IDENTIFY, im_orientation)

        if len (exif_orientation) == 1 and exif_orientation [0].isdigit ():
            try :
                self.__orientation = ORIENTATIONS_MAP [exif_orientation [0][0]]
            except KeyError:
                pass

        if not self.__orientation:
            self.__orientation = ORIENTATION_NONE

        print (self.__orientation)
        return self.__orientation

    def width (self):
        if self.__width >= 0:
            return self.__width

        self.__width = self.__get_width_or_height (get_width = True)
        return self.__width

    def height (self):
        if self.__height >= 0:
            return self.__height

        self.__height = self.__get_width_or_height (get_width = False)
        return self.__height

    def year (self):
        return self.__year if self.__get_exif_date () else ""

    def month (self):
        return self.__month if self.__get_exif_date () else ""

    def month_name (self):
        if self.__month_name:
            return self.__month_name
        if self.__month_name_error:
            return ""

        try:
            self.__month_name = MONTH_NAMES [self.month ()]
        except KeyError:
            self.__month_name = ""

        self.__month_name_error = (self.__month_name == "")
        return self.__month_name

    def month_NAME (self):
        return self.month_name ().upper ()

    def month_Name (self):
        return self.month_name ().capitalize ()

    def day (self):
        return self.__day if self.__get_exif_date () else ""

    def hour (self):
        return self.__hour if self.__get_exif_date () else ""

    def minute (self):
        return self.__minute if self.__get_exif_date () else ""

    def sec (self):
        return self.__sec if self.__get_exif_date () else ""

    def file_name (self):
        if self.__file_name:
            return self.__file_name
        if self.__file_name_error:
            return ""

        self.__file_name = os.path.splitext (os.path.split (self.path)[1])[0]
        self.__file_name_error = (self.__file_name == "")

        return self.__file_name


#- Label template processing -------------------------------------------------#

class WmInitLabelTags:
    # Replace the names of the WmImageMetrics methods in the LABEL_TAGS
    # with the methods themselves for fast and easy call
    _ = LABEL_TAGS.update (((tag, WmImageMetrics.__dict__ [func])
                            for tag, func in LABEL_TAGS.items ()))


class WmLabelSpan:
    '''Part of the label template'''

    def __init__ (self, text):
        self.__text = text
        self.group_start = False
        self.group_end = False

    def value (self, image):
        return None


class WmLabelSpanText (WmLabelSpan):
    '''Plain text part of the label template'''

    def value (self, image):
        return self._WmLabelSpan__text


class WmLabelSpanTag (WmLabelSpan):
    '''
    Tagged part of a label template.
    When composing a label, the tag is replaced by its value
    for the current image.
    '''

    def value (self, image):
        return LABEL_TAGS [self._WmLabelSpan__text] (image)


class WmLabelTemplate:
    '''List of a label template parts'''

    def __init__ (self, template):
        self.__template = template
        self.__spans = None

    def __iter__ (self):
        for span in self.__get_spans ():
            yield span

    def __get_spans (self):
        """
        Template is a PLAIN TEXT and text in [SQUARE BRACKETS].
        Text in [SQUARE BRACKETS] can consist of TAGs (LABEL_TAGS keys)
        mixed with PLAIN TEXT.
        Split label temlate into a sequence of PLAIN TEXT spans and TAG spans.
        """

        if self.__spans:
            return self.__spans

        self.__spans = []

        text_span = ""
        bracket_start = -1
        brackets = 0
        iterator = iter (range (len (self.__template)))
        for i in iterator:
            if brackets == 0:
                if (self.__template [i:].startswith ("[[")
                 or self.__template [i:].startswith ("]]")):
                    text_span += self.__template [i]
                    next (iterator)
                    continue

            if self.__template [i] == "[":
                brackets += 1
                if brackets == 1:
                    tags_start = i + 1
                continue

            if self.__template [i] == "]" and brackets > 0:
                brackets -= 1
                if brackets == 0:
                    if text_span:
                        self.__spans.append (WmLabelSpanText (text_span))
                        text_span = ""
                    # Text in [SQUARE BRACKETS] can contain
                    # TAGs (LABEL_TAGS keys)
                    self.__get_bracket_spans (self.__template [tags_start : i])
                    tags_start = -1
                continue

            if brackets == 0:
                text_span += self.__template [i]

        if brackets > 0:
            text_span += self.__template [tags_start - 1:]
        if text_span:
            self.__spans.append (WmLabelSpanText (text_span))

        return self.__spans

    def __get_bracket_spans (self, string):
        """
        Split string into a sequence of TAG spans and PLAIN TEXT spans.

        string - text in [SQUARE BRACKETS] from the label template,
        can consist of any number of TAGs (LABEL_TAGS keys)
        mixed (or not) with PLAIN TEXT.
        """

        old_len = len (self.__spans)
        text_span = ""
        while True:
            try:
                for tag_name in LABEL_TAGS.keys ():
                    if string.startswith (tag_name):
                        if text_span:
                            self.__spans.append (WmLabelSpanText (text_span))
                            text_span = ""
                        self.__spans.append (WmLabelSpanTag (tag_name))
                        string = string [len (tag_name):]
                        break
                else:
                    text_span += string [0]
                    if string.startswith ("[[") or string.startswith ("]]"):
                        string = string [2:]
                    else:
                        string = string [1:]
            except IndexError:
                break

        if text_span:
            self.__spans.append (WmLabelSpanText (text_span))

        # Mark bracketed label spans in list
        if old_len < len (self.__spans):
            self.__spans [old_len].group_start = True
            self.__spans [-1].group_end = True


class WmLabel:
    """
    Translate label template to label text.
    Adjust label to fit image size.
    """

    def __init__ (self, template, alignment):
        self.__label = WmLabelTemplate (template) if template else None
        self.gravity = ALIGNMENT_TO_GRAVITY_MAP [alignment]
        self.set_image (None)

    def set_image (self, image):
        self.image = image
        self.__font_size = None
        self.__exact_font_size = None
        self.__stroke_width = None
        self.__line_width = None

    def __compose (self):
        '''
        Translate the label template to a label for the current image.
        '''
        if not self.__label:
            return ""

        label_text = ""
        group = False
        group_empty = False
        group_text = ""
        for span in self.__label:
            if span.group_start:
                group = True
                group_empty = False

            if group:
                if not group_empty:
                    value = span.value (self.image)

                    # Return an empty string if ANY tag in a group of spans
                    # (from [SQUARE BRACKETS] in label template) is undefined:
                    # Correct: "[Month DD, YYYY]" -> ""
                    #          "[YYYY year]"      -> ""
                    # Wrong:   "[Month DD, YYYY]" -> " , "
                    #          "[YYYY year]"      -> " year"
                    if not value:
                        group_empty = True
                        group_text = ""
                    else:
                        group_text += value
            else:
                label_text += span.value (self.image)

            if span.group_end:
                label_text += group_text
                group = False
                group_text = ""

        return label_text

    def __calc_font_size (self):
        '''
        Fit label font size to image size.
        '''
        if self.__font_size:
            return

        self.__font_size = LABEL_FONT_SIZE
        self.__exact_font_size = LABEL_FONT_SIZE
        self.__stroke_width = 2

        max_side = min (max (self.image.width (), self.image.height ()),
                        PHOTO_MAX_SIDE)
        if max_side != LABEL_FONT_SIZE_PHOTO_SIDE:
            self.__font_size = int (LABEL_FONT_SIZE *
                                    (float (max_side) /
                                     LABEL_FONT_SIZE_PHOTO_SIDE))
            self.__exact_font_size = self.__font_size
            if self.__font_size < 16:
                self.__font_size = 16
            if self.__font_size < 26:
                self.__stroke_width = 1

        return self.__font_size

    def __split_lines (self, label_text):
        '''
        Split label text to lines to fit image width.
        '''
        res = textwrap.wrap (label_text, width = self.line_width)
        for i in range (len (res) - 1):
            res [i] += '\n'
        return res

    @property
    def font_size (self):
        self.__calc_font_size ()
        return self.__font_size

    @property
    def exact_font_size (self):
        self.__calc_font_size ()
        return self.__exact_font_size

    @property
    def stroke_width (self):
        self.__calc_font_size ()
        return self.__stroke_width

    @property
    def line_width (self):
        '''
        Adjust line width to fit image width and font size.
        '''
        if self.__line_width:
            return self.__line_width

        # Adjust to fit image width
        if self.image.width () >= self.image.height ():
            self.__line_width = LABEL_LINE_WIDTH
        else:
            self.__line_width = int (LABEL_LINE_WIDTH *
                                     (float (self.image.width ()) /
                                      self.image.height ()))

        # Adjust to real font size
        if self.exact_font_size != self.font_size:
            self.__line_width = int (self.__line_width  *
                                     (float (self.exact_font_size) /
                                      self.font_size))

        return self.__line_width

    def write_to_file (self, dir):
        """
        Write label to utf-8 file
        (old ImageMagick can't read national letters from command line)
        """

        label_text = self.__compose ()
        if not label_text:
            return ""

        label_file = get_temp_file_name (dir, "MAGIC_LABEL", "txt")
        if not label_file:
            return ""

        try:
            with open (label_file, 'w', encoding='utf-8') as file:
                file.writelines (self.__split_lines (label_text))
        except OSError as error:
            print (str (error))
            print ("ERROR! Can't create label file:\n  " + label_file)
            return ""

        return label_file


#- Photo files converting ----------------------------------------------------#

class WmFiles:
    """
    Convert files for uploading to wikimapia.
    """

    def __init__ (self, paths):
        self.paths = paths
        self.target_root = ""

        self.label = None

        # Backup original photo when converting in place
        self.backup_enabled = True

        self.new_dirs = []
        self.reset ()

    def reset (self):
        self.start_time = 0
        self.source_exist = False
        self.files_found = 0
        self.files_converted = 0

    def set_target (self, target):
        self.target_root = normalize_path (target)
        if path_exist (self.target_root) and not path_is_dir (self.target_root):
            print ("ERROR! Destination is not a folder:\n  " + target)
            return False
        return True

    def convert (self):
        self.reset ()
        self.start_time = time.time ()

        files = []
        dirs = []
        for path in self.paths:
            src = normalize_path (path)
            if not path_exist (src):
                print ("ERROR! Source not found:\n  " + path)
                continue

            if self.target_root:
                src_dir = os.path.split (src)[0]
                if (src_dir == self.target_root or
                    (not src_dir and self.target_root == ".")):
                    print ("ERROR! Source and destination files " +
                           "are the same:\n  " + src)
                    print ("To replace the original file with the " +
                           "converted one,\n"
                           "don't specify the --destination folder "
                           "and use the --nobackup option.\n")
                    continue

            if path_is_dir (src):
                dirs.append (normalize_path (src))
            else:
                files.append (normalize_path (src))

        self.source_exist = (len (dirs) > 0) or (len (files) > 0)

        self.__process_dirs (dirs)
        self.__process_files (files)

        self.__clean_new_dirs ()

    def print_stats (self):
        if not self.start_time:
            return

        if not self.files_found:
            if self.source_exist:
                print ("Supported images not found. Supported file types:\n" +
                       "\n".join ([(" ." + s) for s in FILE_EXTENSIONS]))
            return

        total_time = time.time () - self.start_time
        if total_time < 0:
            total_time = 0

        files_per_sec = "???"
        sec_per_file = "???"
        if total_time > 0 and self.files_converted > 0:
            files_per_sec = "{: 7.2f}".format (float (self.files_converted) /
                                               total_time)
            sec_per_file = "{: 7.2f}".format (total_time /
                                              self.files_converted)

        print ("\n"
               "Files found      = {:4d}\n".format (self.files_found) +
               "Files converted  = {:4d}\n".format (self.files_converted) +
               "Files per second = " + files_per_sec + "\n" +
               "Time per file    = " + sec_per_file + " sec\n" +
               "Total time       = {: 7.2f} sec\n".format (total_time))

    def __convert_file (self, source, target, backup):
        """
        Convert source photo with the ImageMagick convert
        """

        if target == backup:
             return

        image = WmImageMetrics (source)
        self.label.set_image (image)

        # 1) Downscale a large photo to <PHOTO_MAX_SIDE> pixels on the long side
        resize = ""
        if image.width () > PHOTO_MAX_SIDE or image.height () > PHOTO_MAX_SIDE:
            # a) Horisontal (landscape) photo
            if image.width () > image.height ():
                resize = " -resize " + str (PHOTO_MAX_SIDE) + "x"
            # b) Vertical (portrait) photo
            else:
                resize = " -resize " + "x" + str (PHOTO_MAX_SIDE)

        source_dir, source_name = os.path.split (source)
        target_dir, target_name = os.path.split (target)

        # 2) Create a photo label and write it to the utf-8 text file
        label_cmd = ""
        label_file = self.label.write_to_file (target_dir)
        if label_file:
            label_cmd = (
                ' ' +
                '-gravity ' + self.label.gravity + ' ' +
                '-pointsize ' + str (self.label.font_size) + ' ' +
                '-fill "' + LABEL_COLOR + '" ' +
                '-stroke black -strokewidth ' + str (self.label.stroke_width) +
                ' ' +
                '-font ' + LABEL_FONT +
                ' -annotate +2+0 @"' + label_file + '"')

        # 3) Backup original photo
        src = source
        if backup and source != backup:
            try:
                shutil.move (source, backup)
                src = backup
            except OSError as error:
                print (str (error))
                print ("ERROR! Can't move source file to backup:\n  " +
                       source + "\nto:\n  " +
                       backup + "\n");

        # 4) Resizing and labeling
        im_resize = (
            '"' + src + '" ' +
            '-auto-orient' +
            resize + ' ' +
            '-quality ' + str (PHOTO_QUALITY) + '% ' # Level of compression
            '-strip' +                               # Remove all metadata
                                                     # (EXIF, etc.)
            label_cmd +
            ' "' + target + '"')

        if cmd_exitcode (IM_CONVERT, im_resize) == 0:
            self.files_converted += 1
        else:
            print ("ERROR! Resize failed.\n")
            if src != source:
              try:
                  shutil.move (src, source)
              except OSError as error:
                  print (str (error))
                  print ("ERROR! Can't revert source file from backup:\n  " +
                         src + "\nto:\n  " +
                         source + "\n");

        # 5) Delete temp files
        try:
            if label_file and path_exist (label_file):
                os.remove (label_file)
        except OSError as error:
            print (str (error))
            print ("ERROR! Can't remove temporary label file:\n  " +
                   label_file + "\n");

    def __good_type (self, file):
        ext = os.path.splitext (file) [1][1:]
        res = ext.lower () in FILE_EXTENSIONS

        if res:
            self.files_found += 1

        return res


    def __make_backup_root (self, source_root):
        dir, name = os.path.split (source_root)
        if not name:
            name = dir
            dir = ""

        prefix = (name + "_") if path_is_dir (source_root) else ""

        for i in range (100):
            res = os.path.join (dir, prefix +
                                     BACKUP_DIR_NAME +
                                     ("" if i == 0 else str (i)))
            if path_exist (res):
                continue
            create_dir (res)
            if path_is_dir (res):
                self.new_dirs.append (res)
                return res
            else:
                break

        print ("ERROR! Can't create backup dir for path:\n  " +
               source_root + "\n")

        return ""

    def __process_dir_inplace (self, root):
        backup_root = ""
        backup_root_error = False

        for dir, subdirs, files in os.walk (root):
            backup_dir = ""
            backup_dir_error = False

            for file in files:
                if not self.__good_type (file):
                    continue

                if not self.backup_enabled:
                    path = os.path.join (dir, file)
                    self.__convert_file (path, path, "")
                    continue

                if not backup_dir and not backup_dir_error:
                    if not backup_root and not backup_root_error:
                        backup_root = self.__make_backup_root (root)
                        backup_root_error = (backup_root == "")

                    if backup_root:
                        if dir == root:
                            backup_dir = backup_root
                        else:
                            backup_dir = get_target_path (root,
                                                          backup_root,
                                                          dir)
                            create_dir (backup_dir)
                            if not path_is_dir (backup_dir):
                                backup_dir = ""
                        backup_dir_error = (backup_dir == "")

                path = os.path.join (dir, file)
                backup_path = (os.path.join (backup_dir, file)
                               if backup_dir else
                               os.path.join (dir, (os.path.splitext (file)[0] +
                                                   "_backup" +
                                                   os.path.splitext (file)[1])))

                self.__convert_file (path, path, backup_path)


    def __process_dir (self, source_root):
        if not self.target_root:
            self.__process_dir_inplace (source_root)
            return

        target_root_add_to_new = not path_exist (self.target_root)

        source_upper_root, _ = os.path.split (source_root)
        for dir, subdirs, files in os.walk (source_root):
            target_dir = ""

            for file in files:
                if not self.__good_type (file):
                    continue

                if not target_dir:
                    # source_upper_root is used instead of source_root
                    # so that the script can be conveniently integrated
                    # into file managers:
                    # A subdirectory corresponding to the source_root is created
                    # in the target_root.
                    # The converted files will not be written directly to
                    # target_root but to this subdirectory.
                    target_dir = get_target_path (source_upper_root,
                                                  self.target_root,
                                                  dir)
                    if not create_dir (target_dir):
                        print ("ERROR! Can't create destination folder:\n  " +
                               target_dir)
                        return

                    if target_root_add_to_new:
                        self.new_dirs.append (self.target_root)
                        target_root_add_to_new = False

                source_path = os.path.join (dir, file)
                target_path = os.path.join (target_dir, file)
                self.__convert_file (source_path, target_path, source_path)

    def __process_dirs (self, dirs):
        dirs.sort ()

        for dir in dirs:
            self.__process_dir (dir)

    def __process_files_inplace (self, files):
        root = ""
        root_processed = False
        backup_root = ""

        for file in files:
            if not self.__good_type (file):
                continue

            if not self.backup_enabled:
                self.__convert_file (path, path, "")
                continue

            dir, name = os.path.split (file)
            if root != dir:
                root_processed = False
            if not root_processed:
                root = dir
                backup_root = self.__make_backup_root (file)
                root_processed = True

            backup_file = (os.path.join (backup_root, name)
                           if backup_root else
                           os.path.join (dir, (os.path.splitext (name)[0] +
                                               "_backup" +
                                               os.path.splitext (name)[1])))

            self.__convert_file (file, file, backup_file)

    def __process_files (self, files):
        files.sort ()

        if not self.target_root:
            self.__process_files_inplace (files)
            return

        target_root_created = False
        target_root_add_to_new = not path_exist (self.target_root)
        for file in files:
            if not self.__good_type (file):
                continue

            if not target_root_created:
                if not create_dir (self.target_root):
                    print ("ERROR! Can't create destination folder:\n  " +
                           self.target_root)
                    return
                target_root_created = True

                if target_root_add_to_new:
                    self.new_dirs.append (self.target_root)
                    target_root_add_to_new = False

            dir, name = os.path.split (file)
            target_file = os.path.join (self.target_root, name)

            self.__convert_file (file, target_file, file)

    def __clean_new_dirs (self):
        """Remove all newly created directories if they are useless (empty)."""
        self.new_dirs.sort ()

        try:
            for dir in self.new_dirs:
                files_not_found = True

                for cur_dir, subdirs, files in os.walk (dir):
                    if len (files) > 0:
                        files_not_found = False
                        break

                if files_not_found:
                    shutil.rmtree (dir, ignore_errors=True)
        except OSError:
            pass


#-----------------------------------------------------------------------------#

def main ():
    p = argparse.ArgumentParser (
             description=
                 "Convert photo collection for uploading to wikimapia.org:\n"
                 " - Downscale to ~ 1920 x 1440 (wikimapia reduces the resolution to ~ 960 x 720)\n"
                 " - Compress (wikimapia can't upload file greater than ~ 2 Mb)\n"
                 " - Remove EXIF data (anyway wikimapia drops EXIF)\n"
                 " - Add text label if needed (date, file name, etc.)\n"
                 "\n"
                 "Requirements:\n"
                 " - Python 3\n"
                 " - ImageMagick (http://www.imagemagick.org)\n",
             usage=
                 "%(prog)s "
                 "[--destination=<folder>] "
                 "[--nobackup] "
                 "[--label=<template>] "
                 "[--label_alignment=<corner>] "
                 "<source dir> | <source file>"
                 "... ",
             epilog=####CHECK
                 'Examples:\n'
                 '%(prog)s image.jpg\n'
                 '%(prog)s image.jpg --destination "Photos/To Wikimapia"\n'
                 '%(prog)s image.jpg --nobackup\n'
                 '%(prog)s "Photos/Some file.jpg" "Photos/Some folder" --destination "Photos/Temp"\n'
                 '%(prog)s image.jpg --label"[YYYY]" --label_alignment BottomLeft\n'
                 '%(prog)s image.jpg --label"[YYYY-MM-DD hh:mm:ss]"\n'
                 '%(prog)s image.jpg --label"[YYYY-MM-DD ]Image description"\n'
                 '%(prog)s place1.jpg place2.jpg --label"[Month YYYY, ][file_name]"\n'
                 '%(prog)s "Photos/Central park" --label"Central park"\n',
             formatter_class=argparse.RawTextHelpFormatter) # Manual linewrapping

    p.add_argument ("-v", "--version",
                    action="version",
                    version="%(prog)s " + __version__)
    p.add_argument ("-d", "--destination",
                    dest="target",
                    action="store",
                    default="",
                    help="Destination folder\n"
                         "(if not defined, the files will be\n"
                         "converted in the original folder)")
    p.add_argument ("-n", "--nobackup",
                    action="store_true",
                    default=False,
                    help="Don't keep original photo when converting in place\n"
                         "(--destination folder not defined)")
    p.add_argument ("-l", "--label",
                    action="store",
                    default="",
                    help="Add a text label to the photo according to the template.\n"
                         "This is any text and TAGS in square brackets.\n"
                         "Examples for photo file HAPPY_SHOT.JPG was taken on\n"
                         "August 20, 2020 at 16:33:53 (according to EXIF):\n"
                         " any text                   -> any text\n"
                         " [YYYY-MM-DD hh:mm:ss]      -> 2020-08-20 16:33:53\n"
                         " [file_name]                -> HAPPY_SHOT\n"
                         " [Month YYYY, ][file_name]  -> August 2020, HAPPY_SHOT\n"
                         " [MONTH YYYY, ](C) Author   -> AUGUST 2020, (C) Author\n"
                         " [month DD, YYYY. ]Any text -> august 20, 2020. Any text\n"
                         " [[square brackets]]        -> [square brackets]\n")
    p.add_argument ("-a", "--label_alignment",
                    choices=[ALIGNMENT_TOP_LEFT,
                             ALIGNMENT_TOP_RIGHT,
                             ALIGNMENT_BOTTOM_LEFT,
                             ALIGNMENT_BOTTOM_RIGHT],
                    default = ALIGNMENT_BOTTOM_RIGHT,
                    help = "Place the label in one of the image corners.")
    p.add_argument ("path", nargs = '*',
                    help = "Paths to files and/or folders for processing.")

    args = p.parse_args ()

    if not args.path:
        p.print_help ()
        return


    files = WmFiles (args.path)

    if not files.set_target (args.target):
        return
    files.backup_enabled = not args.nobackup
    files.label = WmLabel (args.label, args.label_alignment)

    files.convert ()
    files.print_stats ()


if __name__ == "__main__":
    main ()
