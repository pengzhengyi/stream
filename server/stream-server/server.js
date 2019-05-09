/* imports */
const cors = require('cors');
const express = require('express');
const handlers = require('./handlers.js');
const env = require('./env.js');
const path = require('path');

const app = express();
const port = 8888;

app.use(cors({
    origin: [`http://localhost:${env.frontendPort}`, `http://${env.IP}:${env.frontendPort}`],
}))

app.use('/music', express.static(path.join(__dirname, 'resources')));

app.get('/music/path/:i', handlers.sendMusicPath);
app.get('/music/catalog', handlers.sendMusicCatalog);


app.get('*', handlers.notFoundHandler);

app.listen(port, env.IP, () => console.log(`stream server listening on port ${port}!`));