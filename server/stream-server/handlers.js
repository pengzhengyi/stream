/* imports */
const libServer = require('./serve_library.js');


let lib = libServer.latestLibInKind('mlib');
let entries = libServer.useLib(lib);

function sendMusicCatalog(req, res) {
    res.json(entries);
}


function sendMusicPath(req, res) {
    if (!req.params.i) {
        const errmsg = "req does not have i field";
        res.status(400).send(errmsg);
        return;
    }
    const index = req.params.i;
    
    let filepath;
    try {
        filepath = libServer.get_filepath(entries, index, relative=false);
        res.sendFile(filepath, {root: __dirname})
    } catch(error) {
        res.status(400).send(error.message);
        return;
    }
}


function notFoundHandler(req, res) {
    res.sendStatus(404);
}


module.exports = {
    sendMusicPath, sendMusicPath,
    sendMusicCatalog: sendMusicCatalog,
    notFoundHandler: notFoundHandler
}
