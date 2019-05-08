import React, { Component } from 'react';
import { library } from '@fortawesome/fontawesome-svg-core'
import { faBackward, faForward, faPause, faPlay } from '@fortawesome/free-solid-svg-icons'
import { servaddr } from './env.js';
import './App.css';
import Catalog from './Catalog.js';

library.add(faBackward, faForward, faPause, faPlay)

class App extends Component {
    constructor(props) {
        super(props);

        this.servaddr = servaddr;

        this.state = {
            catalog: {}
        };
        
    }

    componentDidMount() {
        this.getCatalog();
    }

    getCatalog = () => {
        fetch(`${this.servaddr}/music/catalog`)
        .then(res => res.json())
        .then(catalog => this.setState({catalog: catalog}))
    }

  render() {
    return (
      <div className="App">
        <h1>Stream Player</h1>
        <Catalog catalog={this.state.catalog}></Catalog>
      </div>
    );
  }
}

export default App;
