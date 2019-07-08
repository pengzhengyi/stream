import os
import string
import sys
import subprocess

import File
import Print
import Input


cmderr_template = string.Template("$ ${cmd}\t[${returncode}]\n${stderr}\n")
vformats = {
    'popular': {'.avi', '.flv', '.wmv', '.mov', '.mp4'}
}


def _print_cp_error(cperr, quiet):
    """
    Pretty prints a CalledProcessError
    Args:
        cperr: an subprocess.CalledProcessError
    Returns:
        None, message should be printed
    """
    Print.out(cmderr_template.safe_substitute(cmd=' '.join(cperr.cmd),
                                              returncode=cperr.returncode,
                                              stderr=cperr.stderr), quiet)


class ConvertException(Exception):
    pass


def video2audio(filepath, saveto, output_fmt,
                parse_danmu, skip_existing, quiet):
    """
    converts an video file to an audio file using ffmpeg

    Args:
        filepath: The file path to the input file
        saveto: The filepath to the output file
        output_fmt: which format the audio file is going to be saved as
        parse_danmu: whether danmu in xml format, if exists,
            will be converted to ass format
        skip_existing: whether existing output file with same name will
            be skipped or overwritten
        quiet: Whether error is printed
    Returns:
        Whether the conversion is successful
    """
    if saveto.endswith(output_fmt):
        saveas = saveto
    else:
        saveas = "%s%s" % (saveto, output_fmt)

    if parse_danmu:
        danmu_file = File.find_danmu_file(tgt_file=filepath)
        if danmu_file:
            danmu2ass(danmu_file)

    if os.path.isfile(saveas):
        if skip_existing:
            Print.out("^ skipped %s" % saveas)
            return True

        if Input.confirm('Remove existing %s?' % saveas):
            os.remove(saveas)
        else:
            return True

    # -i
    #     input
    # -vn (output)
    #     Disable video recording
    # -acodec codec (input/output)
    #     Set the audio codec. This is an alias for "-codec:a".
    try:
        cmd = ["ffmpeg", "-i", filepath, "-vn", "-acodec", "copy", saveas]
        subprocess.run(cmd, capture_output=True, check=True, encoding="utf-8")
        Print.out("+ converted %s to %s" % (filepath, saveto), quiet)
        return True
    except subprocess.CalledProcessError as cperr:
        _print_cp_error(cperr, quiet)
        return False


def dir_video2audio(base_dir=None, file_filter=None, to=None,
                    output_fmt=".aac", parse_danmu=False, fail_on_first=True,
                    skip_existing=True, quiet=False):
    """
    converts video files to audio files using ffmpeg

    Args:
        base_dir: The base directory to find video files
            default to current working directory
        file_filter: A filepath will be yielded when
            1. file_filter is not supplied
            2. evaulating file_filter on filename returns True
            default to validating extension
        saveto: The filepath to the output file
            default to save directory
        output_fmt: which format the audio file is going to be saved as
            default to aac
        parse_danmu: whether danmu in xml format, if exists,
            will be converted to ass format, default to False
        fail_on_first: whether the conversion will be aborted immediately
            on first error
        skip_existing: whether existing output file with same name will
            be skipped or overwritten, default to skipping
        quiet: Whether error is silenced
            default to False
    Returns:
        Whether the conversion is successful
    """
    def vffilter(filename):
        _, ext = os.path.splitext(filename)
        return ext in vformats['popular']

    if file_filter is None:
        file_filter = vffilter

    if base_dir is None:
        base_dir = os.getcwd()

    if to is None:
        to = base_dir

    if not os.path.exists(base_dir):
        raise ConvertException("path (%s) not exists" % base_dir)

    result = True
    for filepath in File.files_in_dir(base_dir, file_filter):
        filename, _ = os.path.splitext(os.path.basename(filepath))

        saveto = os.path.join(to, '%s%s' % (filename, output_fmt))
        if not video2audio(filepath, saveto, output_fmt,
                           parse_danmu, skip_existing, quiet):
            if fail_on_first:
                return False
            else:
                result = False
    return result


converter_fp = os.path.join(sys.path[0], "danmaku2ass", "danmaku2ass.py")


def danmu2ass(filepath, converter_fp=converter_fp,
              input_format="autodetect", screensize="1920x1200",
              font="MS PGothic", fontsize="48", opacity="0.5",
              dm="15", ds="15", quiet=False):
    """

    Args:
        See usage below
        quiet: Whether error is silenced
            default to False
    Returns:
        Whether the conversion is susccessful
    usage: danmaku2ass.py [-h] [-f FORMAT] [-o OUTPUT] -s WIDTHxHEIGHT
                      [-fn FONT] [-fs SIZE] [-a ALPHA] [-dm SECONDS]
                      [-ds SECONDS] [-fl FILTER] [-p HEIGHT] [-r]
                      FILE [FILE ...]

    positional arguments:
    FILE                  Comment file to be processed

    optional arguments:
    -h, --help            show this help message and exit
    -f FORMAT, --format FORMAT
                            Format of input file (autodetect|Bilibili|Tudou2|
                            MioMio|Acfun|Niconico|Tudou) [default: autodetect]
    -o OUTPUT, --output OUTPUT
                            Output file
    -s WIDTHxHEIGHT, --size WIDTHxHEIGHT
                            Stage size in pixels
    -fn FONT, --font FONT
                            Specify font face [default: sans-serif]
    -fs SIZE, --fontsize SIZE
                            Default font size [default: 25]
    -a ALPHA, --alpha ALPHA
                            Text opacity
    -dm SECONDS, --duration-marquee SECONDS
                            Duration of scrolling comment display [default: 5]
    -ds SECONDS, --duration-still SECONDS
                            Duration of still comment display [default: 5]
    -fl FILTER, --filter FILTER
                            Regular expression to filter comments
    -p HEIGHT, --protect HEIGHT
                            Reserve blank on the bottom of the stage
    -r, --reduce          Reduce the amount of comments if stage is full
    """
    if not os.path.isfile(filepath):
        raise ConvertException("path (%s) not exists" % filepath)

    if not filepath.endswith('.xml'):
        raise ConvertException("%s not in xml extension" % filepath)

    filename, _ = os.path.splitext(filepath)
    saveas = filename + '.ass'

    cmd = ["python3", converter_fp, "-o", saveas, "-f", input_format,
           "-s", screensize, "-fn", font, "-fs", fontsize, "-a", opacity,
           "-dm", dm, "-ds", ds, "-r", filepath]
    try:
        subprocess.run(cmd, capture_output=True, check=True, encoding="utf-8")
        Print.out("+ parsed danmu file for %s to %s" % (filepath, saveas),
                  quiet)
        return True
    except subprocess.CalledProcessError as cperr:
        _print_cp_error(cperr, quiet)
        return False
