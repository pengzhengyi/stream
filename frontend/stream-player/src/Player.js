import React, { Component } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { servaddr } from './env.js';

function shuffle(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

function mod(n, m) {
    return ((n % m) + m) % m;
}

class Player extends Component {

    constructor(props) {
        super(props);
        this.state = {
            indexes: undefined,
            bi: undefined,
            buffer: [],
            play: false,
        };
        this.audio = undefined;
        this.controlColor = "white";
        this.controlSize = "lg";
    }

    componentDidUpdate(prevProps, prevState) {
        if (prevState.bi === undefined && this.props.indexes !== undefined) {
            const bi = this.props.si === undefined ? 0 :
                this.props.indexes.indexOf(this.props.si);
            this.setState({
                bi: bi,
                buffer: this.props.indexes.slice(0),
            }, () => this.setAudioByBufIndex(bi));
        }

        if (prevProps.si !== this.props.si) {
            const si = Number.parseInt(this.props.si);
            const bi = this.props.indexes.indexOf(si);
            this.setState({bi: bi}, () => this.setAudioByBufIndex(bi, {startPlaying: true}));
        }
        
        if (this.props.onIOS) {
            this.audio = document.getElementsByTagName('audio')[0];
        }
    }

    togglePlay = () => {
        if (this.audio) {
            this.setState({ play: !this.state.play }, () => {
                this.state.play ? this.audio.play() : this.audio.pause();
            });
        }
    }
    
    load = () => {
        if (this.audio) {
            this.audio.load();
        }
    }

    play = () => {
        if (this.audio) {
            this.audio.play();
            this.setState({play: true});
        }
    }
    
    pause = () => {
        if (this.audio) {
            this.audio.pause();
            this.setState({play: false});
        }
    }

    shift = (step, loopBack=false, loopForward=false) => {
        if (step === 0) {
            return;
        }
        let bi = this.state.bi;

        const lenBuf = this.state.buffer.length;
        const pi = bi + step;
        bi = pi;
        if (pi >= lenBuf) {
            if (loopBack) {
                bi = pi % lenBuf;
            } else {
                bi = lenBuf
            }
        } else if (pi < 0) {
            if (loopForward) {
                mod(pi, lenBuf);
            } else {
                bi = 0;
            }
        }

        this.setState({bi: bi}, () => this.setAudioByBufIndex(bi, {startPlaying: true}));
    }

    shuffle = () => {
        this.setState({buffer: shuffle(this.state.buffer)});
    }

    next = () => this.shift(1, {loopBack: false});
    prev = () => this.shift(1, {loopForward: false});

    getCurFileIndex = () => {
        return this.state.buffer[this.state.bi];
    }

    getFileSrcByIndex = (i) => {
        return `${servaddr}/music/path/${i}`;
    }

    getCurFileSrcByIndex = () => {
        if (this.props.onIOS) {
            if (this.audio) {
                this.load();
            }
        }

        return this.getFileSrcByIndex(this.getCurFileIndex());
    }

    setAudioByIndex = (i, startPlaying=false) => {
        this.load();

        if (!this.props.onIOS) {
            this.audio = new Audio(this.getFileSrcByIndex(i));
        }

        this.audio.onended = this.next;
        if (startPlaying) {
            this.play();
        }
    }
    
    setAudioByBufIndex = (bi, startPlaying=false) => {
        this.setAudioByIndex(this.state.buffer[bi], startPlaying);
    }
    
    render() {
        return (
            <div className="player">
                <p className="itemname">{this.props.getName(this.getCurFileIndex())}</p>
                {
                    this.state.bi !== undefined && this.props.onIOS ?
                    (<audio controls preload="auto" onPlay={this.iosReload}>
                        <source src={this.getCurFileSrcByIndex()} type={"audio/" + this.props.getExtension(this.getCurFileIndex())}>
                        </source>
                    </audio>) : (
                        <div className="controls">
                            <div onClick={this.prev}>
                                <FontAwesomeIcon icon="backward" color={this.controlColor} size={this.controlSize} />
                            </div>
                            <div onClick={this.togglePlay}>
                                <FontAwesomeIcon icon={this.state.play ? "pause" : "play"} color={this.controlColor} size={this.controlSize} />
                            </div>
                            <div onClick={this.next}>
                                <FontAwesomeIcon icon="forward" color={this.controlColor} size={this.controlSize} />
                            </div>
                        </div>
                    )
                }
            </div>
        );
    }
}

export default Player;
