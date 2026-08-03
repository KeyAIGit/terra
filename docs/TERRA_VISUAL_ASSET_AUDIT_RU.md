# TERRA — аудит визуальных ассетов

**Дата:** 2026-08-02  
**Статус:** локально проверенный baseline; не список уже приобретённых ассетов

## Вывод

В проекте пока нет фотореалистичного художественного слоя. `Content` занимает
примерно 7,4 МБ и содержит 70 `.uasset` и одну карту. Видимые здания, люди и
предметы в `/Game/Terra` являются legacy proxy/blockout. Они пригодны для
проверки данных и масштаба, но не для оценки финального вида.

## Что доступно локально

- Unreal Engine 5.8.1, Metal SM6, Lumen, Virtual Shadow Maps, Substrate,
  Nanite и hardware ray tracing на Apple M3 Max (30 GPU cores, 36 ГБ unified
  memory).
- Fab `0.0.14` и Quixel Bridge `2025.0.1` как инструменты импорта.
- PCG, Water, World Partition/HLOD, Mass, ZoneGraph, StateTree, Smart Objects,
  Control Rig, IK Rig, Motion Matching и базовый MetaHuman pipeline.
- MetaHuman Crowd pipeline и базовые body/face/retargeting ассеты.
- Простые mannequin locomotion-анимации из UE templates.

Наличие импортёра не означает наличие самой библиотеки: локальных Fab,
Megascans, VaultCache, City Sample, Game Animation Sample и готового
исторического modular kit не обнаружено.

## Текущий блокер MetaHuman

В установке отсутствует каталог
`Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Optional`, включая
`TextureSynthesis` и `BodyTextures`. Локальный лог UE сообщает, что MetaHuman
Creator инициализирован с ограниченными возможностями, а generator toolset не
зарегистрирован. Сначала нужно установить **MetaHuman Creator Core Data** через
компоненты UE 5.8 в Epic Games Launcher.

## Минимальный набор для первого художественного среза

1. Один согласованный modular kit для выбранной культуры и климата: плоские
   крыши, парапеты, дворы, ворота, арки, лестницы, окна, двери и корректные
   collision/LOD.
2. Набор поверхностей и decals: adobe/mudbrick, известковая штукатурка,
   камень, утрамбованная земля, дерево, металл, ткань, грязь, трещины и
   водяные потёки.
3. Локально оправданная растительность и 30–50 бытовых/рыночных props.
4. Core Data, один hero MetaHuman, 6–12 crowd identities, историческая одежда,
   обувь и оптимизированные волосы.
5. Locomotion и 40–60 бытовых анимаций: разговор, торговля, ремесло, сидение,
   переноска и взаимодействие с предметами.
6. Ambient audio и footsteps по типам поверхности.

Каждый внешний набор проходит отдельную проверку: совместимость с UE 5.8 и
Mac/Metal, масштаб, collision, LOD/Nanite, производительность, источник,
Fab ID, автор, лицензия, дата получения и право распространения cooked build
и исходных `.uasset`.

## Первый бюджет производительности

- 1–3 hero-персонажа высокого качества рядом с камерой;
- 20–50 активных NPC, остальные — более дешёвые LOD/cards/instancing;
- Lumen для интерактивного режима, Path Tracing только для офлайн-кадров;
- после добавления 4K-материалов нужен отдельный texture/VT budget: текущий
  streaming pool в 1 ГБ недостаточен для плотной фотограмметрии.

Это стартовые ограничения до реального benchmark на художественном контенте,
а не подтверждённая цифра FPS.
