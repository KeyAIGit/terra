# TERRA Pixel Streaming 2 — localhost

Этот контур даёт один локальный browser-клиент для Unreal Engine 5.8. Он
намеренно не является production-деплоем: HTTP и оба WebSocket endpoint
слушают только `127.0.0.1`, лимит — один player, ICE servers пусты, а
STUN/TURN/SFU/REST API отключены.

## Зафиксированные зависимости

- официальный `EpicGames/PixelStreamingInfrastructure`, ветка `UE5.8`;
- commit `1d1e515e97c026d1f376f329d5f005f58eabb234`;
- release `0.1.0`;
- официальный Node `v22.14.0` для `darwin-arm64`;
- точные значения и SHA-256 архива находятся в `dependency-lock.json`.

Checkout и Node runtime лежат в `Tools/`, но исключены из Git. Чтобы
воспроизвести их на другом Apple Silicon Mac, из корня `Terra`:

```bash
git clone --depth 1 --single-branch --branch UE5.8 \
  https://github.com/EpicGames/PixelStreamingInfrastructure.git \
  Tools/PixelStreamingInfrastructure-UE5.8
git -C Tools/PixelStreamingInfrastructure-UE5.8 \
  checkout --detach 1d1e515e97c026d1f376f329d5f005f58eabb234

curl --fail --location --proto '=https' --tlsv1.2 \
  --output node-v22.14.0-darwin-arm64.tar.gz \
  https://nodejs.org/dist/v22.14.0/node-v22.14.0-darwin-arm64.tar.gz
printf '%s  %s\n' \
  e9404633bc02a5162c5c573b1e2490f5fb44648345d64a958b17e325729a5e42 \
  node-v22.14.0-darwin-arm64.tar.gz | shasum -a 256 -c -
mkdir -p Tools/.runtime
tar -xzf node-v22.14.0-darwin-arm64.tar.gz -C Tools/.runtime
```

Не запускайте непроверенный архив и не применяйте `npm audit fix --force`:
это изменит зафиксированный upstream dependency graph.

Проверка `npm audit --omit=dev` после `npm ci` показывает 0 runtime
vulnerabilities. Полный audit показывает 5 замечаний только в upstream
dev-tooling (4 moderate, 1 high); production launcher эти пакеты не загружает.

## Сборка, запуск и проверка

Из корня `Terra`:

```bash
Scripts/PixelStreaming/bootstrap_local.sh
Scripts/PixelStreaming/check_local.sh --dependencies-only
Scripts/PixelStreaming/start_local.sh
Scripts/PixelStreaming/check_local.sh
Scripts/PixelStreaming/stop_local.sh
```

После запуска открыть `http://127.0.0.1:8080/player.html`. Проверенный
ground-level reality slice запускается отдельно с URL GameMode и параметрами:

```text
"/Engine/Maps/Entry?game=/Script/TerraRuntime.TerraRealitySliceGameMode" -game
-PixelStreamingConnectionURL=ws://127.0.0.1:8888 -RenderOffScreen -ForceRes
-ResX=1920 -ResY=1080
```

Логи и PID находятся только в игнорируемом `Saved/PixelStreaming/`. Скрипт
`stop_local.sh` перед сигналом сверяет, что PID действительно принадлежит
этому launcher, поэтому не завершает посторонний процесс.

## Граница этого режима

Browser-mode работает только на той же машине. Для внешнего интернета нужны
TLS, authentication, TURN/STUN, firewall, rate limits, orchestration и
отдельный security review; эти возможности здесь специально отсутствуют.
