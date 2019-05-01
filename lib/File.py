import os


def files_in_dir(base_dir, file_filter):
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


def find_danmu_file(tgt_file, base_dir=None, ext=".xml"):
    """
    Find a danmu file of target video file

    Args:
        tgt_file: the target video file
        base_dir: the directory to look for the base file
            default to the parent directory of tgt_file
            if pareent directory of tgt_file is undefined,
                default to current directory
        ext: expected extension of danmu file
            default to '.xml'
    Returns:
        The first danmu file for the target video file or None
    """
    tgt_file, _ = os.path.splitext(tgt_file)
    basename = os.path.normpath(tgt_file)

    def danmufilter(filename):
        _, fext = os.path.splitext(filename)
        return ext == fext and basename in filename

    if base_dir is None:
        base_dir = os.path.dirname(basename) or os.getcwd()

    return next(files_in_dir(base_dir, file_filter=danmufilter), None)
