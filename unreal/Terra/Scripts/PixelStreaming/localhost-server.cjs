'use strict';

const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { createRequire } = require('node:module');

function fail(message) {
  process.stderr.write(`ERROR: ${message}\n`);
  process.exit(1);
}

function parseArguments(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!['--config', '--infra-root', '--log-dir'].includes(key) || !value) {
      fail(`Unknown or incomplete argument: ${key}`);
    }
    result[key.slice(2)] = value;
    index += 1;
  }
  for (const key of ['config', 'infra-root', 'log-dir']) {
    if (!result[key]) {
      fail(`Missing required argument --${key}`);
    }
  }
  return result;
}

function loadConfig(configPath) {
  let config;
  try {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (error) {
    fail(`Cannot read config ${configPath}: ${error.message}`);
  }

  const exact = (condition, message) => {
    if (!condition) fail(`Unsafe config rejected: ${message}`);
  };
  exact(config.schema_version === 1, 'schema_version must be 1');
  exact(config.bind_address === '127.0.0.1', 'bind_address must be 127.0.0.1');
  exact(config.player_port === 8080, 'player_port must be 8080');
  exact(config.streamer_port === 8888, 'streamer_port must be 8888');
  exact(config.max_players === 1, 'max_players must be 1');
  exact(Number.isInteger(config.player_keepalive_timeout_ms) && config.player_keepalive_timeout_ms > 0,
    'player_keepalive_timeout_ms must be a positive integer');
  exact(config.homepage === 'player.html', 'homepage must be player.html');
  exact(Array.isArray(config.ice_servers) && config.ice_servers.length === 0,
    'ice_servers must be empty');
  for (const key of ['enable_stun', 'enable_turn', 'enable_sfu', 'enable_rest_api']) {
    exact(config[key] === false, `${key} must be false`);
  }
  return Object.freeze(config);
}

function isLoopback(remoteAddress) {
  return remoteAddress === '127.0.0.1'
    || remoteAddress === '::1'
    || remoteAddress === '::ffff:127.0.0.1';
}

const args = parseArguments(process.argv.slice(2));
const configPath = fs.realpathSync(args.config);
const infraRoot = fs.realpathSync(args['infra-root']);
const logDir = path.resolve(args['log-dir']);
const config = loadConfig(configPath);
const webRoot = path.join(infraRoot, 'SignallingWebServer', 'www');
const homepage = path.join(webRoot, config.homepage);
const wilburPackage = path.join(infraRoot, 'SignallingWebServer', 'package.json');

if (!fs.existsSync(homepage) || !fs.existsSync(wilburPackage)) {
  fail(`Built Pixel Streaming frontend is missing under ${webRoot}`);
}
fs.mkdirSync(logDir, { recursive: true });

const requireFromWilbur = createRequire(wilburPackage);
const express = requireFromWilbur('express');
const { InitLogging, SignallingServer } = requireFromWilbur(
  '@epicgames-ps/lib-pixelstreamingsignalling-ue5.8'
);

InitLogging({
  logDir,
  logMessagesToConsole: 'basic',
  logLevelConsole: 'info',
  logLevelFile: 'info'
});

const app = express();
app.disable('x-powered-by');
let signallingServer;

app.use((request, response, next) => {
  if (request.headers.host !== `127.0.0.1:${config.player_port}`) {
    response.status(403).type('text/plain').send('localhost host required\n');
    return;
  }
  next();
});

app.get('/terra-health', (_request, response) => {
  response.set('Cache-Control', 'no-store');
  response.json({
    ok: true,
    bind_address: config.bind_address,
    player_port: config.player_port,
    streamer_port: config.streamer_port,
    max_players: config.max_players,
    ice_servers: 0,
    stun: false,
    turn: false,
    sfu: false,
    rest_api: false,
    streamers: signallingServer ? signallingServer.streamerRegistry.count() : 0,
    players: signallingServer ? signallingServer.playerRegistry.count() : 0
  });
});

app.get('/', (_request, response) => response.sendFile(homepage));
app.use(express.static(webRoot, { index: config.homepage, fallthrough: false }));

const httpServer = http.createServer(app);
const localOnly = ({ req }) => isLoopback(req.socket.remoteAddress);
const onePlayerOnly = ({ origin, req }) => {
  if (!isLoopback(req.socket.remoteAddress)) return false;
  if (origin !== `http://127.0.0.1:${config.player_port}`) return false;
  return !signallingServer || signallingServer.playerRegistry.count() < config.max_players;
};

signallingServer = new SignallingServer({
  httpServer,
  streamerPort: config.streamer_port,
  streamerWsOptions: {
    host: config.bind_address,
    verifyClient: localOnly
  },
  playerWsOptions: {
    verifyClient: onePlayerOnly
  },
  peerOptions: { iceServers: [] },
  maxSubscribers: config.max_players,
  playerKeepaliveTimeout: config.player_keepalive_timeout_ms
});

httpServer.on('error', (error) => fail(`HTTP server failed: ${error.message}`));
httpServer.listen({
  host: config.bind_address,
  port: config.player_port,
  exclusive: true
}, () => {
  process.stdout.write(
    `TERRA Pixel Streaming ready: http://${config.bind_address}:${config.player_port}/${config.homepage}\n`
  );
});

let shuttingDown = false;
function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  process.stdout.write(`TERRA Pixel Streaming stopping on ${signal}\n`);
  const forceExit = setTimeout(() => process.exit(1), 5000);
  forceExit.unref();
  httpServer.close(() => process.exit(0));
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
