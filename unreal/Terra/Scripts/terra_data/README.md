# TERRA data bridge

Безопасный мост между актуальным экспортом `export_ue` (`run_id=terra-life`)
и Unreal Engine 5.8. Он не изменяет `Content` из обычного Python и не знает о
токенах, сетевых сервисах или приватных файлах.

Главный принцип: старый `/Game/Terra` только инвентаризируется. Новый импорт
может появиться лишь в digest-версии `/Game/TerraLife/v_<sha12>`, поэтому
legacy-уровень и его ассеты не перезаписываются.

Имя version root берётся из content revision digest: он объединяет digest
входного export с версией identity scheme. Поэтому смена семантики ID не
пытается переиспользовать уже созданный namespace.

## Состав

- `terra_bridge.py` — CLI на стандартной библиотеке: схема, инварианты,
  хэши, manifest и сравнение с читаемыми метками старого `.umap`.
- `unreal_import_terra_life.py` — явно запускаемый loader для Python внутри
  Unreal Editor. По умолчанию работает как dry run.
- `generated/import_manifest.json` — детерминированная таблица входных
  файлов, хэшей и безопасных Unreal-путей.
- `generated/validation_report.md` — текущий результат в человекочитаемом
  виде.
- `tests/` — unit/integration tests, не требующие Unreal.

## Что именно валидируется

- сцены и `run_id=terra-life`, соответствие имени папки и `meta.scene`;
- типы и обязательные поля `meta.json`, `buildings.json`, `people.json` и
  `proxy_index.json`;
- заявленные и фактические количества зданий, дорог и людей;
- конечность координат, размеры, диапазоны рельефа, шаг grid, направления,
  маршруты, цвета и согласованность `real`/`born`/`real_person`;
- существование только ожидаемых входных файлов без symlink/path traversal;
- PNG IHDR: PNG16 grayscale heightmap, PNG8 grayscale weight masks, RGB(A)
  terrain texture и согласованные размеры;
- OBJ: геометрия, индексы, UV каждого face vertex, безопасные и существующие
  `mtllib`; MTL: материалы и разрешимые texture references;
- SHA-256 и размер каждого из обязательных файлов. Абсолютные source paths в
  manifest запрещены.

## Команды вне Unreal

Из корня проекта:

```bash
python3 Scripts/terra_data/terra_bridge.py validate --json
python3 Scripts/terra_data/terra_bridge.py compare
python3 Scripts/terra_data/terra_bridge.py generate
python3 -m unittest discover -s Scripts/terra_data/tests -v
```

`generate` завершается с кодом 2 и не создаёт manifest, если есть хотя бы
одна ошибка. JSON сериализуется с сортировкой ключей; digest и оба generated
файла повторяемы для одинакового экспорта и legacy inventory.

Текущий подтверждённый результат см. в
`generated/validation_report.md`: три сцены, 150 файлов, 0 ошибок и
0 предупреждений. Старый `L_capital.umap` содержит 302 читаемые метки зданий
и 48 вхождений NPC, а актуальный `capital` — 300 зданий и 48 людей.

## Provisional identity и будущая миграция

Текущие `buildings.json` и `people.json` не содержат стабильных entity IDs.
Bridge поэтому создаёт для каждого здания и человека временный, но
детерминированный UUIDv5 по схеме
`terra.provisional-entity-uuidv5/v1`:

```text
UUIDv5(
  namespace c6e6fa94-b92b-5bae-b40e-62f31a09bdcf,
  canonical_json(run_id, scene, entity_kind, source_index, full source record)
)
```

Сам namespace получен как
`UUIDv5(NAMESPACE_URL, "urn:terra:entity:provisional:v1")` и зафиксирован в
manifest; он не генерируется заново на каждой машине.

Canonical JSON сохраняет Unicode, сортирует ключи, удаляет незначащие
пробелы и запрещает NaN. Manifest также хранит `record_sha256`, status
`provisional` и source index. Для текущих трёх сцен создано 614 уникальных
ID: 502 здания и 112 людей.

Это ID для связывания импортированных actor, runtime state и первой БД, но
не вечная историческая идентичность. Изменение записи или перестановка
массива меняет provisional ID. Поэтому upstream exporter должен добавить
authoritative ID, устойчивый к порядку, редактированию визуальных полей и
повторному экспорту.

Обязательная миграция при появлении authoritative IDs:

1. exporter публикует `entity_id` в каждой source record;
2. data pipeline создаёт проверенную таблицу
   `provisional_id -> authoritative_id`, без many-to-one коллизий;
3. save games, runtime DB, диалоги и ссылки заменяются транзакционно, а
   provisional ID остаются aliases для старых сохранений;
4. после окна совместимости новые записи запрещают provisional IDs.

Loader повторно вычисляет UUID из source перед импортом. Building/person
actors получают tags `EntityId`, `EntityId=<uuid>` и
`ProvisionalIdentity`, чтобы runtime мог связать actor с manifest и при этом
не спутать временный ID с authoritative.

## Безопасный запуск внутри Unreal

Сначала включить Python Editor Script Plugin, открыть Output Log и выбрать
Python. Подставить абсолютный путь проекта:

```python
exec(open("/absolute/path/Terra/Scripts/terra_data/unreal_import_terra_life.py", encoding="utf-8").read(), globals())
result = run("capital", dry_run=True)
```

Dry run:

1. проверяет схему manifest и все Unreal package paths;
2. проверяет все 150 размеров и SHA-256 из source export;
3. сверяет выбранную сцену, counts, proxy types и заново вычисляет каждый
   provisional entity UUID;
4. проверяет, что destination выбранной сцены и её generated level пока
   пусты (другие сцены той же digest-версии не мешают);
5. ничего не создаёт и не сохраняет.

Только после успешного dry run:

```python
result = run("capital", dry_run=False)
```

Loader импортирует terrain/far terrain/water и каждый proxy type в отдельную
папку, создаёт новый `L_capital`, расставляет 300 building actors и 48 person
proxy actors, добавляет свет и PlayerStart, затем сохраняет только новую
digest-версию. Имена над NPC выключены по умолчанию; для look-dev можно
передать `spawn_name_labels=True`.

Повторный импорт той же сцены в тот же version root намеренно запрещён; при
этом `capital`, `bronze` и `neolithic` можно импортировать последовательно в
одну digest-версию. При частично оборванном импорте не удаляйте папку
автоматически: сначала изучите Output Log и содержимое namespace. Новый
export digest или новая версия identity scheme естественно создаст новую
immutable-версию.

## Известные границы первого bridge

- Сравнение legacy `.umap` использует только имена пакетов и восстановимые
  ASCII/UTF-16 actor labels. Это доказательство drift, но не полный parser
  формата UAsset/UMAP.
- Дороги проверены, хэшированы и остаются в scene bible
  `buildings.json`; spline/PCG-геометрия дорог этим первым importer ещё не
  создаётся.
- Жители пока импортируются как proxy meshes. MetaHuman assembly, волосы,
  одежда, skeletal animation, Mass/StateTree и диалоги являются следующими
  слоями и не должны смешиваться с неизменяемой data ingest стадией.
- Скрипт подготовлен и протестирован снаружи UE; реальный editor import нужно
  выполнить только после сохранения текущей открытой карты и успешного dry
  run.
