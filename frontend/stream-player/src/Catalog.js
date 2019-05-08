import React, { Component } from 'react';
import CatalogItem from './CatalogItem.js';
import Player from './Player.js';
import './Catalog.css';

if (!Object.entries) {
  Object.entries = function( obj ){
    let ownProps = Object.keys( obj ),
        i = ownProps.length,
        resArray = new Array(i); // preallocate the Array
    while (i--)
      resArray[i] = [ownProps[i], obj[ownProps[i]]];
    
    return resArray;
  };
}

const onIOS = !!navigator.platform && /iPad|iPhone|iPod/.test(navigator.platform);

class Catalog extends Component {
    constructor(props) {
        super(props);
        this.state = {
            catalog: {},
            si: undefined,
        }
        this.unknown = "Unknown";
    }

    componentDidUpdate(prevProps) {
        if (Object.entries(this.props.catalog).length === 0 
            && this.props.catalog.constructor === Object) {
            return;
        }

        if (prevProps.catalog !== this.props.catalog) {
            this.parseCatalog();
        }
    }


    parseCatalog = () => {
        const catalog = this.props.catalog;
        const indexes = [];
        const parsedCatalog = {};
        Object.entries(catalog).forEach(
            ([index, relpath]) =>  {
                const i = Number.parseInt(index);
                const normpath = this.normalizePath(relpath);
                const {album, artist, shortPath, itemname, extension} = this.parsePath(normpath);
                parsedCatalog[i] = {
                    album: album,
                    artist: artist,
                    origPath: relpath,
                    normPath: normpath,
                    shortPath: shortPath,
                    itemname: itemname,
                    extension: extension
                };
                indexes.push(i);
            });
        indexes.sort((i1, i2) => i1 - i2);
        this.setState({
            catalog: parsedCatalog,
            indexes: indexes,
        });
    }

    normalizePath = (path) => {
        if (path.startsWith('./')) {
            return path.slice(2);
        }
        return path;
    }
    
    parsePath = (longPath) => {
        const unknown = this.unknown;

        let shortPath = longPath;
        let artistName = unknown;
        let albumName = unknown;
        let extension = undefined;
        let itemname = undefined;
        
        /* get artist and album */
        const artistSlashIndex = shortPath.indexOf('/');
        if (artistSlashIndex !== -1) {
            artistName = shortPath.substring(0, artistSlashIndex).trim();
            shortPath = shortPath.substring(artistSlashIndex + 1).trim();
        
            const albumSlashIndex = shortPath.indexOf('/');
            if (albumSlashIndex !== -1) {
                albumName = shortPath.substring(0, albumSlashIndex).trim();
                shortPath = shortPath.substring(albumSlashIndex + 1).trim();
            }
        }
        
        const songPrefixIndex = shortPath.indexOf('-');
        if (songPrefixIndex !== -1) {
            const songPrefix = shortPath.substring(0, songPrefixIndex).trim();
            if (artistName === unknown) {
                artistName = songPrefix;
                shortPath = shortPath.substring(songPrefixIndex + 1).trim();
            } else if ((artistName !== unknown && songPrefix === artistName)
                || (albumName !== unknown && songPrefix === albumName)) {
                shortPath = shortPath.substring(songPrefixIndex + 1).trim();
            }
        }

        const extensionDotIndex = shortPath.lastIndexOf('.');
        if (extensionDotIndex !== -1) {
            itemname = shortPath.substring(0, extensionDotIndex).trim();
            extension = shortPath.substring(extensionDotIndex+1).trim();
        } else {
            itemname = shortPath;
        }

        return {
            album: albumName,
            artist: artistName, 
            shortPath: shortPath,
            itemname: itemname,
            extension: extension
        }
    };

    selectItem = (index) => {
        if (index !== this.state.si) {
            this.setState({si: index});
        }
    }

    getItem = (index) => {
        if (!this.state.catalog[index]) {
            return this.unknown;
        }
        return this.state.catalog[index];
    }
    
    getName = (index) => {
        return this.getItem(index).itemname;
    }


    getExtension = (index) => {
        return this.getItem(index).extension;
    }

    render() {
        return (
            <div>
                <ul className={"catalog" + (onIOS ? " ios" : "")}>
                {
                    Object.entries(this.state.catalog).map(
                    ([index, {normPath, itemname}]) => 
                    <CatalogItem key={index} active={this.state.si === index} path={normPath} itemname={itemname} selectItem={() => this.selectItem(index)}>
                    </CatalogItem>)
                }
                </ul>
                <Player indexes={this.state.indexes} si={this.state.si} onIOS={onIOS} getName={this.getName} getExtension={this.getExtension}></Player>
            </div>
            );
    }
}

export default Catalog;
