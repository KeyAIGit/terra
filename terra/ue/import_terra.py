# -*- coding: utf-8 -*-
"""
TERRA -> Unreal Engine 5: сборка уровня из папки экспорта.

Запуск ВНУТРИ редактора UE 5.4+ (включён Python Editor Script Plugin):
  Window -> Output Log -> в выпадашке командной строки выбрать «Python» ->
  exec(open(r"C:/путь/к/export_ue/import_terra.py", encoding="utf-8").read())

Скрипт сам: создаёт новый уровень, импортирует ландшафт/воду/прокси-меши,
расставляет здания и людей по манифестам, ставит солнце по широте, небо,
туман и пост-обработку. Каждый шаг обёрнут в try/except — одна ошибка не
валит всю сборку; в конце печатается сводка.

Писан консервативно по официальному Python API UE 5.4/5.5; на рискованные
вызовы есть фолбэки (EditorActorSubsystem -> EditorLevelLibrary и т.п.).
"""

import json
import os
import traceback

import unreal

# ═══════════════════════════ НАСТРОЙКИ ═══════════════════════════
# Какую сцену собирать: "capital" | "bronze" | "neolithic"
SCENE = "capital"

# Папка сцены. "auto" — ищем export_ue/<SCENE> рядом с проектом и рядом с
# этим скриптом. Если не найдёт — ПОМЕНЯЙ НА СВОЮ, например:
#   SCENE_DIR = r"C:/Users/you/Documents/Unreal Projects/Terra/export_ue/capital"
SCENE_DIR = "auto"

CONTENT_ROOT = "/Game/Terra"      # куда класть ассеты в Content Browser
MAKE_NEW_LEVEL = True             # создать чистый уровень /Game/Terra/Maps/L_<сцена>
SPAWN_PEOPLE = True               # расставить жителей-капсулы с табличками имён
MAX_NAME_TAGS = 60                # табличек имён максимум (производительность)
# ═════════════════════════════════════════════════════════════════

LOG = {"ok": 0, "warn": 0, "err": 0, "details": []}


def _info(msg):
    unreal.log("[terra] " + msg)


def _warn(msg):
    LOG["warn"] += 1
    LOG["details"].append("WARN: " + msg)
    unreal.log_warning("[terra] " + msg)


def _err(msg):
    LOG["err"] += 1
    LOG["details"].append("ERR : " + msg)
    unreal.log_error("[terra] " + msg)


def step(name, fn, *a, **kw):
    """Выполнить шаг; ошибка шага не валит сборку."""
    try:
        r = fn(*a, **kw)
        LOG["ok"] += 1
        return r
    except Exception:
        _err(name + " -> " + traceback.format_exc(limit=2).replace("\n", " | "))
        return None


# ─────────────────────── сабсистемы с фолбэками ───────────────────────
def _get_subsys(cls):
    try:
        return unreal.get_editor_subsystem(cls)
    except Exception:
        return None


EAS = _get_subsys(unreal.EditorActorSubsystem)          # спавн/удаление акторов
LES = _get_subsys(unreal.LevelEditorSubsystem)          # уровни
EASSET = _get_subsys(unreal.EditorAssetSubsystem)       # ассеты


def spawn_obj(obj, loc, rot=None):
    rot = rot or unreal.Rotator(0.0, 0.0, 0.0)
    if EAS is not None:
        return EAS.spawn_actor_from_object(obj, loc, rot)
    return unreal.EditorLevelLibrary.spawn_actor_from_object(obj, loc, rot)  # deprecated fallback


def spawn_cls(cls, loc, rot=None):
    rot = rot or unreal.Rotator(0.0, 0.0, 0.0)
    if EAS is not None:
        return EAS.spawn_actor_from_class(cls, loc, rot)
    return unreal.EditorLevelLibrary.spawn_actor_from_class(cls, loc, rot)


def destroy(actor):
    try:
        if EAS is not None:
            EAS.destroy_actor(actor)
        else:
            unreal.EditorLevelLibrary.destroy_actor(actor)
    except Exception:
        pass


def load_asset(path):
    try:
        if EASSET is not None:
            return EASSET.load_asset(path)
    except Exception:
        pass
    return unreal.EditorAssetLibrary.load_asset(path)


def list_assets(folder):
    try:
        if EASSET is not None:
            return list(EASSET.list_assets(folder, recursive=True))
    except Exception:
        pass
    try:
        return list(unreal.EditorAssetLibrary.list_assets(folder, recursive=True))
    except Exception:
        return []


# ─────────────────────── поиск папки сцены ───────────────────────
def find_scene_dir():
    if SCENE_DIR != "auto":
        return SCENE_DIR
    cands = []
    try:
        proj = unreal.SystemLibrary.get_project_directory()
        cands += [os.path.join(proj, "export_ue", SCENE),
                  os.path.join(proj, "..", "export_ue", SCENE)]
    except Exception:
        pass
    try:
        cands.append(os.path.join(unreal.Paths.project_dir(), "export_ue", SCENE))
    except Exception:
        pass
    cands.append(os.path.join(os.getcwd(), "export_ue", SCENE))
    for c in cands:
        c = os.path.normpath(c)
        if os.path.isfile(os.path.join(c, "meta.json")):
            return c
    raise RuntimeError(
        "Папка сцены не найдена. Пробовал: " + "; ".join(cands) +
        ". Укажи SCENE_DIR вручную в начале import_terra.py")


def read_json(scene_dir, name):
    with open(os.path.join(scene_dir, name), "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────── импорт OBJ ───────────────────────
def import_obj(filepath, dest_path):
    """Импорт OBJ через AssetImportTask; возвращает список новых путей ассетов.

    Ассеты ищем разницей содержимого папки до/после — это устойчиво к тому,
    как именно Interchange назовёт меш (имя файла или имя объекта в OBJ)."""
    before = set(list_assets(dest_path))
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filepath)
    task.set_editor_property("destination_path", dest_path)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    new_paths = []
    try:
        new_paths = [str(p) for p in task.get_editor_property("imported_object_paths")]
    except Exception:
        pass
    if not new_paths:
        after = set(list_assets(dest_path))
        new_paths = sorted(after - before)
    return new_paths


def first_of_class(paths, cls):
    for p in paths:
        a = load_asset(p.split(".")[0])
        if a is not None and isinstance(a, cls):
            return a
    return None


def import_static_mesh(scene_dir, fname, dest):
    fp = os.path.join(scene_dir, fname)
    if not os.path.isfile(fp):
        _warn("нет файла " + fp + " — пропускаю")
        return None, []
    paths = import_obj(fp, dest)
    mesh = first_of_class(paths, unreal.StaticMesh)
    if mesh is None:
        _warn("после импорта " + fname + " не найден StaticMesh (пути: %s)" % paths)
    return mesh, paths


# ─────────────────────── калибровка осей/масштаба ───────────────────────
def calibrate(terrain_mesh, meta):
    """Определить, как импортер обошёлся с осями/масштабом OBJ.

    Экспорт пишет Z-вверх и сантиметры. Если импортер счёл файл Y-up и
    повернул, высота ландшафта окажется по Y — лечим креном (roll) актора.
    Возвращает (fix_roll_deg, fix_scale, swap_yz)."""
    exp_xy = float(meta["terrain"]["size_cm"])
    exp_z = max(1.0, meta["terrain"]["z_max_cm"] - meta["terrain"]["z_min_cm"])
    bb = terrain_mesh.get_bounding_box()
    ex = bb.max.x - bb.min.x
    ey = bb.max.y - bb.min.y
    ez = bb.max.z - bb.min.z
    _info("габариты импортированного ландшафта: %.0f × %.0f × %.0f см" % (ex, ey, ez))
    # масштаб: по горизонтальной стороне (метры вместо сантиметров и т.п.)
    horiz = max(ex, ey, ez)
    fix_scale = 1.0
    if horiz > 1.0 and abs(horiz - exp_xy) / exp_xy > 0.05:
        fix_scale = exp_xy / horiz
        _warn("масштаб импорта отличается, компенсирую scale ×%.3f" % fix_scale)
    swap = ez > exp_z * 3.0 and min(ex, ey) < exp_xy * 0.5  # высота «уехала» из Z
    if not swap:
        return 0.0, fix_scale, False
    # высота по Y (или X): подбираем крен опытным путём — спавним, меряем, удаляем
    for roll in (90.0, -90.0):
        a = spawn_obj(terrain_mesh, unreal.Vector(0, 0, 0),
                      unreal.Rotator(roll, 0.0, 0.0))  # Rotator(roll,pitch,yaw)
        if a is None:
            continue
        try:
            a.set_actor_scale3d(unreal.Vector(fix_scale, fix_scale, fix_scale))
            o, ext = a.get_actor_bounds(False)
            good = ext.z * 2 < exp_z * 3.0 and ext.x * 2 > exp_xy * 0.5
        except Exception:
            good = False
        destroy(a)
        if good:
            _warn("импортер повернул OBJ (Y-вверх) — компенсирую креном %.0f°" % roll)
            return roll, fix_scale, True
    _warn("не удалось подобрать крен — оставляю без поворота")
    return 0.0, fix_scale, False


def make_rot(yaw_deg, fix_roll):
    # unreal.Rotator(roll, pitch, yaw); UE применяет roll -> pitch -> yaw,
    # поэтому крен-компенсация и наш yaw просто складываются в одном ротаторе
    return unreal.Rotator(fix_roll, 0.0, float(yaw_deg))


def make_scale(sx, sy, sz, fix_roll, fix_scale):
    # масштаб актора — по ЛОКАЛЬНЫМ осям меша: при крене ±90° локальная Y
    # смотрит вверх, поэтому Y и Z меняются местами
    if abs(fix_roll) > 45.0:
        sy, sz = sz, sy
    return unreal.Vector(sx * fix_scale, sy * fix_scale, sz * fix_scale)


# ─────────────────────── материалы ───────────────────────
def make_color_material(name, folder, hex_color, two_sided=True):
    """Простой Material с константным цветом. None, если API недоступно."""
    try:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        full = folder + "/" + name
        if unreal.EditorAssetLibrary.does_asset_exist(full):
            return load_asset(full)
        mat = tools.create_asset(name, folder, unreal.Material,
                                 unreal.MaterialFactoryNew())
        if mat is None:
            return None
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        mel = unreal.MaterialEditingLibrary
        node = mel.create_material_expression(
            mat, unreal.MaterialExpressionConstant3Vector, -320, 0)
        node.set_editor_property("constant", unreal.LinearColor(r, g, b, 1.0))
        mel.connect_material_property(node, "", unreal.MaterialProperty.MP_BASE_COLOR)
        rough = mel.create_material_expression(
            mat, unreal.MaterialExpressionConstant, -320, 220)
        rough.set_editor_property("r", 0.85)
        mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        if two_sided:
            mat.set_editor_property("two_sided", True)
        mel.recompile_material(mat)
        return mat
    except Exception:
        return None


def make_texture_material(name, folder, texture, two_sided=True):
    try:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        full = folder + "/" + name
        if unreal.EditorAssetLibrary.does_asset_exist(full):
            return load_asset(full)
        mat = tools.create_asset(name, folder, unreal.Material,
                                 unreal.MaterialFactoryNew())
        if mat is None:
            return None
        mel = unreal.MaterialEditingLibrary
        ts = mel.create_material_expression(
            mat, unreal.MaterialExpressionTextureSample, -380, 0)
        ts.set_editor_property("texture", texture)
        mel.connect_material_property(ts, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
        rough = mel.create_material_expression(
            mat, unreal.MaterialExpressionConstant, -380, 260)
        rough.set_editor_property("r", 0.92)
        mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        if two_sided:
            mat.set_editor_property("two_sided", True)
        mel.recompile_material(mat)
        return mat
    except Exception:
        return None


def make_translucent_material(name, folder, hex_color, opacity=0.7):
    try:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        full = folder + "/" + name
        if unreal.EditorAssetLibrary.does_asset_exist(full):
            return load_asset(full)
        mat = tools.create_asset(name, folder, unreal.Material,
                                 unreal.MaterialFactoryNew())
        if mat is None:
            return None
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        mel = unreal.MaterialEditingLibrary
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property("two_sided", True)
        node = mel.create_material_expression(
            mat, unreal.MaterialExpressionConstant3Vector, -320, 0)
        node.set_editor_property("constant", unreal.LinearColor(r, g, b, 1.0))
        mel.connect_material_property(node, "", unreal.MaterialProperty.MP_BASE_COLOR)
        op = mel.create_material_expression(
            mat, unreal.MaterialExpressionConstant, -320, 220)
        op.set_editor_property("r", opacity)
        mel.connect_material_property(op, "", unreal.MaterialProperty.MP_OPACITY)
        mel.recompile_material(mat)
        return mat
    except Exception:
        return None


def mesh_has_materials(mesh):
    try:
        mats = mesh.get_editor_property("static_materials")
        return any(m.material_interface is not None for m in mats)
    except Exception:
        return False


def slot_names(mesh):
    try:
        return [str(m.material_slot_name) for m in
                mesh.get_editor_property("static_materials")]
    except Exception:
        return []


def apply_slot_materials(mesh, mats_by_slot, ordered_slots):
    """Назначить свои материалы на слоты МЕША по имени; фолбэк — по порядку.

    Свои материалы двусторонние — страховка от возможного разворота
    нормалей/обхода при конвертации осей OBJ импортером."""
    if mesh is None or not mats_by_slot:
        return 0
    n = 0
    try:
        names = slot_names(mesh)
        for i, nm in enumerate(names):
            hit = None
            low = nm.lower()
            for slot, mat in mats_by_slot.items():
                if slot in low:
                    hit = mat
                    break
            if hit is None and len(names) == len(ordered_slots):
                hit = mats_by_slot.get(ordered_slots[i])
            if hit is not None:
                mesh.set_material(i, hit)
                n += 1
    except Exception:
        pass
    return n


def override_slot_color(actor, slot_name, mat):
    """Назначить материал на слот по имени (walls/roof/trim) на КОМПОНЕНТЕ."""
    if mat is None:
        return False
    try:
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh = comp.get_editor_property("static_mesh")
        for i, nm in enumerate(slot_names(mesh)):
            if slot_name in nm.lower():
                comp.set_material(i, mat)
                return True
    except Exception:
        pass
    return False


# ─────────────────────── сцена: свет, небо, туман ───────────────────────
def build_lighting(meta, mats_folder):
    lat = float(meta.get("latitude_deg", 30.0))
    elev = float(meta.get("sun", {}).get("elevation_deg", 55.0))
    yaw = -55.0 if lat >= 0 else 125.0        # солнце с юга (+Y) / с севера
    sun = step("DirectionalLight", spawn_cls, unreal.DirectionalLight,
               unreal.Vector(0, 0, 20000), unreal.Rotator(0.0, -elev, yaw))
    if sun:
        sun.set_actor_label("Sun_TERRA")
        try:
            lc = sun.get_component_by_class(unreal.DirectionalLightComponent)
            lc.set_editor_property("intensity", 9.0)
            lc.set_editor_property("atmosphere_sun_light", True)
        except Exception:
            _warn("не смог настроить компонент солнца (не страшно)")
    sky = step("SkyAtmosphere", spawn_cls, unreal.SkyAtmosphere,
               unreal.Vector(0, 0, 0))
    if sky:
        sky.set_actor_label("SkyAtmosphere_TERRA")
    sl = step("SkyLight", spawn_cls, unreal.SkyLight, unreal.Vector(0, 0, 12000))
    if sl:
        sl.set_actor_label("SkyLight_TERRA")
        try:
            slc = sl.get_component_by_class(unreal.SkyLightComponent)
            slc.set_editor_property("real_time_capture", True)
        except Exception:
            _warn("SkyLight без real_time_capture — включи вручную при желании")
    fog = step("ExponentialHeightFog", spawn_cls, unreal.ExponentialHeightFog,
               unreal.Vector(0, 0, meta["terrain"]["z_min_cm"]))
    if fog:
        fog.set_actor_label("Fog_TERRA")
        try:
            fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
            fc.set_editor_property("fog_density", 0.012)
            fc.set_editor_property("start_distance", 3000.0)
        except Exception:
            pass
    ppv = step("PostProcessVolume", spawn_cls, unreal.PostProcessVolume,
               unreal.Vector(0, 0, 0))
    if ppv:
        ppv.set_actor_label("PostProcess_TERRA")
        try:
            ppv.set_editor_property("unbound", True)
        except Exception:
            _warn("PPV не стал unbound")
        try:
            s = ppv.get_editor_property("settings")
            for flag, prop, val in (
                    ("override_auto_exposure_min_brightness",
                     "auto_exposure_min_brightness", 0.35),
                    ("override_auto_exposure_max_brightness",
                     "auto_exposure_max_brightness", 1.6),
                    ("override_bloom_intensity", "bloom_intensity", 0.35),
                    ("override_vignette_intensity", "vignette_intensity", 0.35)):
                try:
                    s.set_editor_property(flag, True)
                    s.set_editor_property(prop, val)
                except Exception:
                    pass  # в 5.5+ часть имён экспозиции другая — просто пропустим
            ppv.set_editor_property("settings", s)
        except Exception:
            _warn("настройки пост-обработки пропущены (останутся дефолты)")


# ─────────────────────── главная сборка ───────────────────────
def run():
    _info("══════════ TERRA -> UE: сцена «%s» ══════════" % SCENE)
    scene_dir = find_scene_dir()
    _info("папка сцены: " + scene_dir)
    meta = read_json(scene_dir, "meta.json")
    buildings = read_json(scene_dir, "buildings.json")
    people = read_json(scene_dir, "people.json")
    proxy_index = {}
    try:
        proxy_index = read_json(scene_dir, os.path.join("proxy_meshes",
                                                        "proxy_index.json"))
    except Exception:
        _warn("нет proxy_index.json — масштабирую по правилу size/100")

    root = CONTENT_ROOT + "/" + SCENE
    mesh_dir = root + "/Meshes"
    mats_dir = root + "/Materials"

    # 0. новый чистый уровень
    if MAKE_NEW_LEVEL:
        lvl = CONTENT_ROOT + "/Maps/L_" + SCENE
        made = False
        try:
            if LES is not None:
                made = LES.new_level(lvl)
        except Exception:
            made = False
        if not made:
            try:
                made = unreal.EditorLevelLibrary.new_level(lvl)
            except Exception:
                made = False
        if made:
            _info("создан чистый уровень " + lvl)
        else:
            _warn("не смог создать уровень — собираю в ТЕКУЩЕМ уровне")

    # 1. ландшафт
    terrain, terrain_paths = import_static_mesh(scene_dir, "terrain.obj", mesh_dir)
    if terrain is None:
        _err("ландшафт не импортировался — прекращаю (проверь путь и лог выше)")
        return summary()
    fix_roll, fix_scale, swapped = calibrate(terrain, meta)

    # материал ландшафта: запечённая текстура (двусторонний — страховка от
    # возможного разворота нормалей при конвертации осей импортером)
    tex = first_of_class(terrain_paths, unreal.Texture2D)
    if tex is None:
        for p in list_assets(mesh_dir):
            a = load_asset(str(p).split(".")[0])
            if isinstance(a, unreal.Texture2D) and "terrain_color" in str(p):
                tex = a
                break
    tmat = None
    if tex is not None:
        tmat = make_texture_material("M_TerraTerrain", mats_dir, tex)
    if tmat is None:
        tmat = make_color_material("M_TerraTerrainFlat", mats_dir, "#8f9c55")
    if tmat is not None:
        if apply_slot_materials(terrain, {"terrain": tmat, "default": tmat},
                                ["terrain"]) == 0:
            _warn("не смог назначить материал ландшафта — останется импортный")
    elif not mesh_has_materials(terrain):
        _warn("у ландшафта нет материала (API материалов недоступно) — "
              "назначь любой материал вручную")

    ta = step("спавн ландшафта", spawn_obj, terrain, unreal.Vector(0, 0, 0),
              make_rot(0.0, fix_roll))
    if ta:
        ta.set_actor_label("Terrain_TERRA")
        if fix_scale != 1.0:
            ta.set_actor_scale3d(unreal.Vector(fix_scale, fix_scale, fix_scale))

    # 2. дальнее кольцо и вода
    far, _ = import_static_mesh(scene_dir, "terrain_far.obj", mesh_dir)
    if far is not None:
        fm = make_color_material("M_TerraFar", mats_dir, "#9aa060")
        apply_slot_materials(far, {"far": fm, "default": fm}, ["far"])
        fa = step("спавн кольца", spawn_obj, far, unreal.Vector(0, 0, 0),
                  make_rot(0.0, fix_roll))
        if fa:
            fa.set_actor_label("TerrainFar_TERRA")
            if fix_scale != 1.0:
                fa.set_actor_scale3d(unreal.Vector(fix_scale, fix_scale, fix_scale))
    if meta["terrain"].get("water_z_cm") is not None:
        water, _ = import_static_mesh(scene_dir, "water.obj", mesh_dir)
        if water is not None:
            wm = make_translucent_material("M_TerraWater", mats_dir, "#2e6f86", 0.72)
            apply_slot_materials(water, {"water": wm, "default": wm}, ["water"])
            wa = step("спавн воды", spawn_obj, water, unreal.Vector(0, 0, 0),
                      make_rot(0.0, fix_roll))
            if wa:
                wa.set_actor_label("Water_TERRA")
                if fix_scale != 1.0:
                    wa.set_actor_scale3d(unreal.Vector(fix_scale, fix_scale,
                                                       fix_scale))

    # 3. прокси-меши типов зданий + свои материалы по слотам walls/roof/trim
    proxies = {}
    kinds = sorted(set(b["type"] for b in buildings["buildings"])) + ["person"]
    for kind in kinds:
        m, _p = import_static_mesh(
            scene_dir, os.path.join("proxy_meshes", kind + ".obj"),
            mesh_dir + "/Proxies")
        if m is None:
            continue
        proxies[kind] = m
        pi = proxy_index.get(kind) or {}
        slots = pi.get("slots") or ["walls", "roof", "trim"]
        colors = pi.get("colors") or {}
        mats = {}
        for slot in slots:
            hexc = colors.get(slot, "#b0a080")
            mats[slot] = make_color_material(
                "M_%s_%s" % (kind, slot), mats_dir + "/Proxies", hexc)
        if any(v is not None for v in mats.values()):
            apply_slot_materials(m, mats, slots)
    _info("импортировано прокси-мешей: %d/%d" % (len(proxies), len(kinds)))

    # 4. здания по манифесту
    n_b, n_b_err = 0, 0
    for b in buildings["buildings"]:
        try:
            mesh = proxies.get(b["type"])
            if mesh is None:
                n_b_err += 1
                continue
            x, y, z = b["pos_cm"]
            sx, sy, sz = (max(0.02, v / 100.0) for v in b["size_cm"])
            a = spawn_obj(mesh, unreal.Vector(x, y, z),
                          make_rot(b["yaw_deg"], fix_roll))
            if a is None:
                n_b_err += 1
                continue
            a.set_actor_scale3d(make_scale(sx, sy, sz, fix_roll, fix_scale))
            a.set_actor_label("B_%s_%d" % (b["type"], n_b))
            try:
                a.set_folder_path("Terra/Buildings")
            except Exception:
                pass
            n_b += 1
        except Exception:
            n_b_err += 1
    _info("зданий расставлено: %d (ошибок %d из %d)"
          % (n_b, n_b_err, len(buildings["buildings"])))

    # 5. люди: прокси-человек + табличка имени
    n_p, n_p_err = 0, 0
    if SPAWN_PEOPLE:
        person = proxies.get("person")
        cloth_cache = {}
        for i, p in enumerate(people["people"]):
            try:
                x, y, z = p["spawn_cm"]
                rot = make_rot(p.get("yaw_deg", 0.0), fix_roll)
                if person is not None:
                    a = spawn_obj(person, unreal.Vector(x, y, z), rot)
                else:
                    a = spawn_cls(unreal.StaticMeshActor, unreal.Vector(x, y, z), rot)
                if a is None:
                    n_p_err += 1
                    continue
                a.set_actor_label("NPC_" + p["name"])
                try:
                    a.set_folder_path("Terra/People")
                except Exception:
                    pass
                hexc = p.get("cloth_hex", "#8a6a4e")
                if hexc not in cloth_cache:
                    cloth_cache[hexc] = make_color_material(
                        "M_Cloth_" + hexc.lstrip("#"), mats_dir, hexc)
                override_slot_color(a, "walls", cloth_cache[hexc])
                if i < MAX_NAME_TAGS:
                    t = spawn_cls(unreal.TextRenderActor,
                                  unreal.Vector(x, y, z + 205.0),
                                  unreal.Rotator(0.0, 0.0, 180.0))
                    if t is not None:
                        t.set_actor_label("Name_" + p["name"])
                        try:
                            trc = t.get_component_by_class(unreal.TextRenderComponent)
                            trc.set_text(p["name"] + "  ·  " + p.get("role_ru", ""))
                            trc.set_world_size(26.0)
                            # ВНИМАНИЕ: у unreal.Color позиционный порядок (b,g,r,a)
                            trc.set_text_render_color(
                                unreal.Color(r=240, g=230, b=200, a=255))
                            try:
                                trc.set_horizontal_alignment(
                                    unreal.HorizTextAligment.EHTA_CENTER)
                            except Exception:
                                pass
                            t.set_folder_path("Terra/People")
                        except Exception:
                            pass
                n_p += 1
            except Exception:
                n_p_err += 1
        _info("людей расставлено: %d (ошибок %d из %d)"
              % (n_p, n_p_err, len(people["people"])))

    # 6. свет, небо, туман, пост-обработка, точка старта
    build_lighting(meta, mats_dir)
    ps = meta.get("player_start_cm")
    if ps:
        pa = step("PlayerStart", spawn_cls, unreal.PlayerStart,
                  unreal.Vector(ps[0], ps[1], ps[2] + 60.0))
        if pa:
            pa.set_actor_label("PlayerStart_TERRA")

    # 7. сохранить
    try:
        unreal.EditorAssetLibrary.save_directory(CONTENT_ROOT, recursive=True)
    except Exception:
        _warn("не сохранил ассеты автоматически — сохрани Ctrl+Shift+S")
    try:
        if LES is not None:
            LES.save_current_level()
        else:
            unreal.EditorLevelLibrary.save_current_level()
    except Exception:
        _warn("не сохранил уровень автоматически — сохрани Ctrl+S")

    return summary(n_b, n_b_err, n_p, n_p_err)


def summary(n_b=0, n_b_err=0, n_p=0, n_p_err=0):
    _info("══════════════ СВОДКА ══════════════")
    _info("сцена: %s   зданий: %d (ошибок %d)   людей: %d (ошибок %d)"
          % (SCENE, n_b, n_b_err, n_p, n_p_err))
    _info("шагов успешно: %d, предупреждений: %d, ошибок: %d"
          % (LOG["ok"], LOG["warn"], LOG["err"]))
    for line in LOG["details"][:30]:
        _info("  " + line)
    if LOG["err"] == 0:
        _info("ГОТОВО. Нажми Play (или встань во вьюпорте у PlayerStart_TERRA).")
    else:
        _info("Собралось с ошибками — смотри строки ERR выше; "
              "их можно прислать Фейблу как есть.")
    return LOG


run()
