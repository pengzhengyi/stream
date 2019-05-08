import React, { Component } from 'react';

class CatalogItem extends Component {
    render() {
        return (
            <li 
                className={`catalog-item${this.props.active ? " active": ""}`}
                title={this.props.path} 
                onClick={this.props.selectItem}>
                {this.props.itemname}
            </li>
        );
    }
}

export default CatalogItem;
