const fs = require('fs');
const path = require('path')


const libDir = './data';
const resourcesDir = './resources'

/**
 * all libraries in directory 
 * {
 *    mlib: [mlibfile1, mlibfile2, ...],
 *    vlib: [vlibfile1, vlibfile2, ...],
 *    ...
 * }*/
const filenames = fs.readdirSync(libDir);
const libs = {};
for (let filename of filenames) {
    let ext = path.extname(filename);
    if (!ext || !ext.endsWith('lib')) {
        continue;
    }
    ext = ext.slice(1);
    if (ext in libs) {
        libs[ext].push(filename);
    } else {
        libs[ext] = [filename];
    }
}


/* get latest library of a kind */
function getLibTimestamp(libfilename) {
    libfilename = path.basename(libfilename);
    const i = libfilename.indexOf('_');
    console.assert(i !== -1);
    return libfilename.substring(0, i);
}


function latestLibInKind(kind) {
    const klibs = libs[kind];
    klibs.sort(function(libfile1, libfile2) {
        return getLibTimestamp(libfile2) - getLibTimestamp(libfile1);
    });
    return klibs[0];
}


/**
 * resources directory will be symlinked to the base directory of library
 * the catalog will be returned
 */
function useLib(filename) {
    /* validate and read library file */
    const filepath = path.join(libDir, filename);
    if (!fs.existsSync(filepath)) {
        throw new Error(`${filepath} does not exists`);
    }

    const content = fs.readFileSync(filepath, 'utf-8');

    const entrySep = '\n';
    const lines = content.split(entrySep);

    if (!lines) {
        throw new Error(`empty content in (${filepath})`);
    }

    /* validate and symlink base directory */
    const baseDir = lines[0];
    if (!baseDir) {
        throw new Error(`cannot interpret base directory from first line of ${filepath}`);
    }
    
    if (!fs.existsSync(baseDir)) {
        throw new Error(`${baseDir} does not exists`);
    }

    if (fs.existsSync(resourcesDir)) {
        fs.unlinkSync(resourcesDir);
    }

    fs.symlinkSync(baseDir, resourcesDir);


    /* build a dictionary of file entries */
    const entries = {}
    for (let i = 1; i < lines.length; ++i) {
        const line = lines[i];
        const [index, relpath] = line.split((/ (.+)/));
        if (index && relpath) {
            entries[index] = relpath;
        }
    }
    return entries;
}


function get_filepath(entries, index, relative=true) {
    if (!index in entries) {
        throw new Error(`not a valid index ${index} in ${Object.keys(entries)}`);
    }

    const relpath = entries[index];
    const filepath = path.join(resourcesDir, relpath);
    if (!fs.existsSync(filepath)) {
        throw new Error(`${filepath} does not exists`);
    }

    return relative? relpath: filepath;
}


module.exports = {
    libs: libs,
    useLib: useLib,
    get_filepath: get_filepath,
    latestLibInKind: latestLibInKind
}