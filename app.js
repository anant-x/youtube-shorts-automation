#!/usr/bin/env node
/**
 * Entry point for YouTube Shorts OAuth + upload.
 * Run from this folder:  node app.js
 *                       node app.js --authenticate
 */
const path = require("path");
process.chdir(path.join(__dirname));
require("./upload.js");
