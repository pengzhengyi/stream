/* imports */
const express = require('express');
const handlers = require('./handlers.js');
const path = require('path')

const app = express();
const port = 8888;

app.use('/music', express.static(path.join(__dirname, 'resources')));

app.get('/music/path/:i', handlers.sendMusicPath);
app.get('/music/catalog', handlers.sendMusicCatalog);


app.get('*', handlers.notFoundHandler);

app.listen(port, () => console.log(`stream server listening on port ${port}!`));