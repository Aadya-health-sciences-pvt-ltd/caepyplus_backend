const http = require('http');

function makeRequest(path, data) {
    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: '127.0.0.1',
            port: 8000,
            path: path,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(data)
            }
        }, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => resolve({statusCode: res.statusCode, body}));
        });
        
        req.on('error', e => reject(e));
        req.write(data);
        req.end();
    });
}

async function run() {
    try {
        console.log("Starting session...");
        const startRes = await makeRequest('/api/v1/voice/start', JSON.stringify({}));
        console.log("Start status:", startRes.statusCode);
        const startData = JSON.parse(startRes.body);
        const sessionId = startData.session_id;
        
        console.log("Sending chat...");
        const chatRes = await makeRequest('/api/v1/voice/chat', JSON.stringify({
            session_id: sessionId,
            user_transcript: "hello"
        }));
        console.log("Chat status:", chatRes.statusCode);
        console.log("Chat body:", chatRes.body);
    } catch (e) {
        console.error(e);
    }
}

run();
