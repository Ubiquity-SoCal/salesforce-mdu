import { LightningElement } from 'lwc';

export default class MduHomePage extends LightningElement {
    executiveLoaded = false;

    handleExecutiveActive() {
        this.executiveLoaded = true;
    }
}
