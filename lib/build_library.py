import os
import random
import sys
import time


_version = sys.version_info
if _version < (3, 7):
    time.time_ns = lambda: int(time.time * 1e6)


class BuildException(Exception):
    pass


# build functions
def build_lib(base_dir, to, filetype, file_filter, entry_sep, quiet):
    """
    Generates a library file
        example:
            suppose /dev contains foo.txt and bar.txt
            /dev
            0 foo.txt
            1 bar.txt

    Args:
        base_dir: The base directory to start building library file
        to: An absolute path of a directory inside which
            the library file will be saved
        filetype: The extension the library filename will be saved as
        file_filter: A filepath will be yielded when
            1. file_filter is not supplied
            2. evaulating file_filter on filename returns True
        entry_sep: How each file entry is separated
        quiet: Whether progress is printed

    Returns:
        Number of file entries written

    Raises:
        BuildException:
            raises when
            1. base_dir does not exist
            1. <to> is not an absolute path
                (relative path is not guaranteed to work)
            2. <to> does not point to a directory
    """
    def out(msg):
        if not quiet:
            print(msg)

    if not os.path.exists(base_dir):
        raise BuildException("path (%s) not exists" % base_dir)

    out("building library from %s" % base_dir)

    saveat = _filepath_to_save(to, filetype)
    with open(saveat, 'w+') as lib_writer:
        lib_writer.write(base_dir + entry_sep)

        for i, filepath in enumerate(_files_in_dir(base_dir, file_filter)):
            file_msg = '%d %s' % (i, filepath)
            out("+ discovered " + file_msg)
            lib_writer.write(file_msg + entry_sep)

    return i + 1


# build location
def default_lib_savedir():
    """
    gets the default location to save the library file

    Args:
        None

    Returns:
        The default directory to save the library file
            $PROJECT_DIR/stream/data
    """
    project_dir = runpath = sys.path[0]
    while os.path.basename(project_dir) != 'stream':
        if not project_dir:
            err_msg = "cannot locate default save directory from %s" % runpath
            raise BuildException(err_msg)
        project_dir = os.path.dirname(project_dir)
    return os.path.join(project_dir, 'data')


# Custom Builds
def build_music_lib(
        base_dir, to=default_lib_savedir(),
        fmt_choice='main', quiet=True):
    """
    Generates a music library file, see build_lib for more info

    Args:
        base_dir: The base directory to start building library file
            default to default_lib_savedir()
        to: An absolute path of a directory inside which
            the library file will be saved
        fmt_choice: Choices which set of audio formats are accepted
            default to main
        quiet: Whether progress is printed
            default to True

    Returns:
        Number of file entries written

    Raises:
        BuildException:
            raises when
            1. base_dir does not exist
            1. <to> is not an absolute path
                (relative path is not guaranteed to work)
            2. <to> does not point to a directory
    """
    def mffilter(filename):
        _, ext = os.path.splitext(filename)
        return ext in mfmts

    mfmts = set(mformats[fmt_choice]['fmt2mime'].keys())

    return build_lib(
        base_dir, to, filetype='mlib',
        file_filter=mffilter, entry_sep='\n', quiet=quiet)


# formats
mformats = {
    'full': {
        'mime2fmt': {
            'wav': {'.wav', '.wave'},
            'mpeg': {'.mp3'},
            'mp4': {'.mp4', '.m4a', '.m4p', '.m4b', '.m4r', '.m4v'},
            'aac': {'.aac'},
            'flac': {'.flac'},
            'webm': {'.weba', '.webm'},
            'ogg': {'.ogg', '.ogv', '.oga', '.ogx', '.ogm', '.spx', '.opus'}
        },
        'fmt2mime': {
            '.wave': ['wav'],
            '.wav': ['wav'],
            '.mp3': ['mpeg'],
            '.mp4': ['mp4'],
            '.m4v': ['mp4'],
            '.m4a': ['mp4'],
            '.m4r': ['mp4'],
            '.m4p': ['mp4'],
            '.m4b': ['mp4'],
            '.aac': ['aac'],
            '.flac': ['flac'],
            '.webm': ['webm'],
            '.weba': ['webm'],
            '.oga': ['ogg'],
            '.opus': ['ogg'],
            '.ogx': ['ogg'],
            '.ogv': ['ogg'],
            '.spx': ['ogg'],
            '.ogm': ['ogg'],
            '.ogg': ['ogg']
        },
    },
    'main': {
        'mime2fmt': {
            'wav': {'.wav'},
            'mpeg': {'.mp3'},
            'mp4': {'.mp4'},
            'aac': {'.aac'},
            'flac': {'.flac'},
            'webm': {'.weba', '.webm'},
            'ogg': {'.ogg'}
        },
        'fmt2mime': {
            '.wav': ['wav'],
            '.mp3': ['mpeg'],
            '.mp4': ['mp4'],
            '.aac': ['aac'],
            '.flac': ['flac'],
            '.webm': ['webm'],
            '.weba': ['webm'],
            '.ogg': ['ogg']
        }
    }
}


# helper functions
def _files_in_dir(base_dir, file_filter):
    """
    Find all files in a directory satisfying specified condition

    Args:
        base_dir: The base directory to start traversing
        file_filter: A filepath will be yielded when
            1. file_filter is None
            2. evaulating file_filter on filename returns True

    Returns:
        A generator of relative filepaths from base_dir
            e.g. suppose /dev contains foo.txt and bar.txt
                    (foo.txt, bar.txt) will be returned
    """
    for dirpath, _, filenames in os.walk(base_dir):
        relpath = os.path.relpath(dirpath, start=base_dir)
        for filename in filenames:
            if file_filter is None or file_filter(filename):
                yield os.path.join(relpath, filename)


def _custom_libname(filetype, salt_len=2):
    """
    Choose a custom name for library file
        Format:
            filetype: file extensiion
            cur_time: current time
            salt: salt_len number of digits
            <cur_time>_<salt>.<filetype>

    Args:
        filetype: The extension the library filename will be saved as
        salt_len: The length of the salt
            salt is a sequence of random digit
            default to 2

    Returns:
        Library file name string
    """
    filetype = filetype or 'lib'
    cur_time = time.time_ns()
    salt = ''.join(str(d) for d in random.sample(range(10), salt_len))
    return "%d_%s.%s" % (cur_time, salt, filetype)


def _filepath_to_save(to, filetype):
    """
    Choose where to save the library file

    Args:
        to: An absolute path of a directory inside which
            the library file will be saved
        filetype: The extension the library filename will be saved as

    Returns:
        An absolute path to save the library file

    Raises:
        BuildException:
            raises when
            1. <to> is not an absolute path
                (relative path is not guaranteed to work)
            2. <to> does not point to a directory
    """
    if not os.path.isdir(to):
        raise BuildException("invalid path: %s not a directory" % to)

    filepath = os.path.join(to, _custom_libname(filetype))
    while os.path.exists(filepath):
        filepath = os.path.join(to, _custom_libname(filetype))
    return filepath