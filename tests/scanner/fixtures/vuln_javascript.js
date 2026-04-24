// Synthetic vulnerable JavaScript file for B-SCAN-03 testing
// DO NOT USE IN PRODUCTION — intentionally insecure code

const express = require('express');
const child_process = require('child_process');
const app = express();

// === INJ-XSS: Cross-site scripting via innerHTML ===
function displayUser(name) {
    document.getElementById('user').innerHTML = name;
    document.write("<p>" + userInput + "</p>");
}

// === INJ-SQL: SQL injection via template literal ===
app.get('/user', (req, res) => {
    const name = req.query.name;
    db.query(`SELECT * FROM users WHERE name = '${name}'`);
});

// === INJ-CMD: Command injection ===
function runSearch(req) {
    child_process.exec("grep " + req.query.term + " /var/log/app.log");
}

// === AUTH-HARDCODED: Hardcoded credentials ===
const password = "MyS3cretP@ss";
const config = {
    apiKey: "sk-live-abcdef1234567890",
    secret: "hunter2forever",
};

// === SSRF-REQUEST: Server-side request forgery ===
const axios = require('axios');
app.get('/fetch', (req, res) => {
    axios.get(req.query.url).then(r => res.send(r.data));
});

// === CRYPTO-RANDOM: Insecure random ===
function generateToken() {
    return Math.random().toString(36);
}

// === ERR-INFO-LEAK: Error info leak ===
app.use((err, req, res, next) => {
    res.send(err.stack);
});

// === CONF-CORS-WILD: Overly permissive CORS ===
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    next();
});
