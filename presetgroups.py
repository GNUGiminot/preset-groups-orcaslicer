# /// script
# requires-python = ">=3.9"
# [tool.orcaslicer.plugin]
# name = "Preset Groups"
# description = "Sort your own filament, printer and process presets into groups, by hand or by rules; find look-alikes, check, compare and load them into slots."
# author = "GNUGiminot"
# version = "0.2.0"
# ///

"""Preset Groups: an OrcaSlicer plugin that sorts the user's own presets into named groups.

It only reads presets, through Orca's API: preset files are never opened, so names in any script
are safe, and nothing in Orca's own lists changes. Groups live in the plugin's settings.
"""

import json
import os

import orca

# build_wheel.py replaces the next line with presetgroups_core.py itself.
from presetgroups_core import *  # noqa: F401,F403  # BUILD:CORE

LANGUAGES = ("en", "ru")

# Every user-facing string, as (English, Russian). Plural forms are separated by "|":
# English "one|other", Russian "one|few|many"; {n} is the number.
STRINGS = {
    "app.title": ("Preset Groups", "Группы профилей"),
    "app.loading": ("Reading your presets…", "Читаю твои профили…"),
    "app.no_printer": ("No printer selected", "Принтер не выбран"),
    "btn.refresh": ("Read the presets again", "Перечитать профили"),
    "btn.settings": ("Settings", "Настройки"),
    "kind.filament": ("Filaments", "Филаменты"),
    "kind.printer": ("Printers", "Принтеры"),
    "kind.process": ("Processes", "Процессы"),
    "nav.all": ("All presets", "Все профили"),
    "nav.none": ("Not in a group", "Без группы"),
    "nav.groups": ("Groups", "Группы"),
    "nav.check": ("Tidy up", "Порядок"),
    "nav.dups": ("Look-alikes", "Похожие и дубли"),
    "nav.spool": ("From PipSpool", "Из PipSpool"),
    "nav.hidden": ("Hidden here", "Скрытые"),
    "btn.new_group": ("New group", "Новая группа"),
    "groups.empty": ("Make a group and drag presets into it.", "Создай группу и перетащи в неё профили."),
    "side.hint": ("Only your own presets are shown. Groups live in the plugin: Orca's lists and the preset files stay as they are.",
                  "Здесь только твои профили. Группы хранятся в плагине: списки Orca и файлы профилей не меняются."),
    "search.placeholder": ("Search name, type, vendor, group", "Поиск: название, тип, производитель, группа"),
    "n.presets": ("{n} preset|{n} presets", "{n} профиль|{n} профиля|{n} профилей"),
    "n.selected": ("{n} selected|{n} selected", "Выбран {n}|Выбрано {n}|Выбрано {n}"),
    "n.walls": ("{n} wall|{n} walls", "{n} стенка|{n} стенки|{n} стенок"),
    "tb.printer": ("Printer", "Принтер"),
    "tb.printer_current": ("Current printer", "Текущий принтер"),
    "tb.printer_all": ("All printers", "Все принтеры"),
    "tb.sort": ("Sort", "Порядок"),
    "sort.name": ("By name", "По названию"),
    "sort.type": ("By type", "По типу"),
    "sort.model": ("By model", "По модели"),
    "sort.layer": ("By layer height", "По высоте слоя"),
    "sort.vendor": ("By vendor", "По производителю"),
    "row.no_parent": ("No base preset", "Без базового профиля"),
    "row.slot": ("Slot {n}", "Слот {n}"),
    "row.active": ("Active", "Выбран"),
    "row.dup": ("Look-alike", "Похож"),
    "row.other_printer": ("Made for another printer", "Сделан для другого принтера"),
    "u.mm": ("mm", "мм"),
    "u.mm3s": ("mm³/s", "мм³/с"),
    "f.nozzle": ("Nozzle", "Сопло"),
    "f.bed": ("Bed", "Стол"),
    "f.speed": ("Max volumetric speed", "Макс. объёмная скорость"),
    "f.flow": ("Flow ratio", "Коэффициент потока"),
    "f.pa": ("Pressure advance", "Pressure advance"),
    "f.type": ("Type", "Тип"),
    "f.vendor": ("Vendor", "Производитель"),
    "f.model": ("Model", "Модель"),
    "f.nozzle_d": ("Nozzle diameter", "Диаметр сопла"),
    "f.area": ("Bed size", "Размер стола"),
    "f.height": ("Max height", "Макс. высота"),
    "f.layer": ("Layer height", "Высота слоя"),
    "f.walls": ("Walls", "Стенки"),
    "f.infill": ("Infill", "Заполнение"),
    "f.pattern": ("Infill pattern", "Узор заполнения"),
    "f.support": ("Supports", "Поддержки"),
    "yes": ("on", "вкл."),
    "no": ("off", "выкл."),
    "btn.show": ("Show", "Показать"),
    "btn.hide": ("Hide here", "Скрыть здесь"),
    "btn.to_slot": ("To slot", "В слот"),
    "btn.select": ("Select", "Выбрать"),
    "btn.to_group": ("To group", "В группу"),
    "btn.ungroup": ("Out of group", "Убрать из группы"),
    "btn.clear": ("Clear selection", "Снять выбор"),
    "btn.not_dup": ("Not the same", "Это разные"),
    "btn.keep": ("Keep this one", "Оставить этот"),
    "btn.cancel": ("Cancel", "Отмена"),
    "btn.save": ("Save", "Сохранить"),
    "btn.create": ("Create", "Создать"),
    "btn.undo": ("Undo", "Отменить"),
    "empty.none_title": ("No presets of your own yet", "Своих профилей пока нет"),
    "empty.none_filament": ("Filament presets you save in Orca appear here. System and Generic ones are left out.",
                            "Здесь появятся филаменты, которые ты сохранишь в Orca. Системные и Generic не показываются."),
    "empty.none_printer": ("Printer presets you save in Orca appear here.", "Здесь появятся принтеры, которые ты сохранишь в Orca."),
    "empty.none_process": ("Process presets you save in Orca appear here.", "Здесь появятся процессы, которые ты сохранишь в Orca."),
    "empty.filtered_title": ("Nothing here for this filter", "По этому фильтру ничего нет"),
    "empty.filtered": ("Try another printer or clear the search.", "Выбери другой принтер или очисти поиск."),
    "empty.group_title": ("The group is empty", "Группа пустая"),
    "empty.group": ("Drag presets here, or select several and press “To group”.", "Перетащи сюда профили или выдели несколько и нажми «В группу»."),
    "empty.hidden_title": ("Nothing hidden", "Скрытых нет"),
    "empty.hidden": ("Presets you hide here stay in Orca; the plugin just stops showing them.", "Скрытые профили остаются в Orca, плагин просто перестаёт их показывать."),
    "empty.spool_title": ("No PipSpool presets", "Профилей PipSpool нет"),
    "empty.spool": ("Presets PipSpool makes for spools are named “(#12) … - PipSpool”.", "PipSpool называет профили катушек так: «(#12) … - PipSpool»."),
    "empty.dups_title": ("No look-alikes", "Похожих нет"),
    "empty.dups": ("Every preset of this kind differs from the others.", "Все профили этого вида отличаются друг от друга."),
    "group.drop_here": ("Drop presets here", "Перетащи профили сюда"),
    "dups.intro": ("These presets look like one preset saved more than once. Keep one and hide the rest here, or mark them as different. Orca's own files stay untouched.",
                   "Эти профили похожи на один и тот же, сохранённый несколько раз. Оставь один, остальные скрой здесь, или отметь, что они разные. Файлы Orca не меняются."),
    "dups.same": ("Identical settings", "Настройки совпадают полностью"),
    "dups.spool": ("Same vendor, type and colour: probably the same spool", "Тот же производитель, тип и цвет: похоже, одна катушка"),
    "dups.near": ("Differs in {n} setting|Differs in {n} settings", "Отличается {n} параметром|Отличается {n} параметрами|Отличается {n} параметрами"),
    "dups.setting": ("Setting", "Параметр"),
    "drawer.based": ("Based on {parent}", "Основан на {parent}"),
    "drawer.main": ("Main settings", "Основное"),
    "drawer.printers": ("Printers", "Принтеры"),
    "drawer.is_printer": ("This is a printer preset", "Это профиль принтера"),
    "drawer.any_printer": ("Any printer", "Любой принтер"),
    "drawer.changes": ("{n} change from the base preset|{n} changes from the base preset",
                       "{n} изменение от базового профиля|{n} изменения от базового профиля|{n} изменений от базового профиля"),
    "drawer.here": ("Here", "Здесь"),
    "drawer.parent": ("Base", "Базовый"),
    "drawer.no_changes": ("Same as the base preset.", "Совпадает с базовым профилем."),
    "drawer.no_parent": ("This preset has no base preset to compare with.", "У профиля нет базового, сравнивать не с чем."),
    "menu.to_group": ("Move to group", "Переместить в группу"),
    "menu.to_slot": ("Put into filament slot", "Поставить в слот филамента"),
    "menu.no_slots": ("No filament slots", "Нет слотов филамента"),
    "menu.details": ("Details", "Подробнее"),
    "menu.rename": ("Group settings", "Настроить группу"),
    "menu.up": ("Move up", "Выше"),
    "menu.down": ("Move down", "Ниже"),
    "menu.delete": ("Delete group", "Удалить группу"),
    "dlg.new": ("New group", "Новая группа"),
    "dlg.rename": ("Group", "Группа"),
    "dlg.text_filament": ("Any name: by material, by job, by spool shelf.", "Любое название: по материалу, по задаче, по полке с катушками."),
    "dlg.text_printer": ("Any name: by workshop, by nozzle, by owner.", "Любое название: по мастерской, по соплу, по владельцу."),
    "dlg.text_process": ("Any name: by quality, by part type, by customer.", "Любое название: по качеству, по типу деталей, по заказчику."),
    "dlg.placeholder_filament": ("For example, PETG for daily prints", "Например, PETG на каждый день"),
    "dlg.placeholder_printer": ("For example, Workshop", "Например, Мастерская"),
    "dlg.placeholder_process": ("For example, Fast drafts", "Например, Быстрые черновики"),
    "msg.moved": ("{n} moved to “{group}”", "{n} → «{group}»"),
    "msg.ungrouped": ("{n} taken out of the group", "{n}: без группы"),
    "msg.hidden": ("{n} hidden here", "Скрыто здесь: {n}"),
    "msg.shown": ("{n} shown again", "Снова видно: {n}"),
    "msg.not_dup": ("Marked as different", "Отмечены как разные"),
    "msg.group_deleted": ("Group “{group}” deleted; its presets are not in a group now", "Группа «{group}» удалена, её профили теперь без группы"),
    "msg.group_exists": ("A group with this name already exists", "Группа с таким названием уже есть"),
    "msg.applied_slot": ("“{name}” is in slot {slot}", "«{name}» стоит в слоте {slot}"),
    "msg.applied": ("“{name}” selected", "Выбран «{name}»"),
    "err.dirty": ("Save or discard the unsaved changes of “{name}” in Orca first.", "Сначала сохрани или отмени несохранённые изменения «{name}» в Orca."),
    "err.not_found": ("Orca has no preset “{name}” any more. Read the presets again.", "В Orca больше нет профиля «{name}». Перечитай профили."),
    "err.apply": ("Orca did not select the preset: {error}", "Orca не выбрала профиль: {error}"),
    "set.language": ("Language", "Язык"),
    "lang.auto": ("As in Orca", "Как в Orca"),
    "lang.ru": ("Русский", "Русский"),
    "lang.en": ("English", "English"),
    "set.about": ("Preset Groups {version}. Reads presets through Orca's API and never changes their files.",
                  "Группы профилей {version}. Читает профили через API Orca и не меняет их файлы."),
    "nav.new": ("New", "Новые"),
    "nav.fav": ("Favourites", "Избранное"),
    "nav.health": ("Check-up", "Проверка"),
    "row.new": ("New", "Новый"),
    "btn.mark_seen": ("Mark all as seen", "Отметить просмотренными"),
    "msg.seen": ("{n} marked as seen", "Просмотрено: {n}"),
    "new.intro": ("Presets that appeared since you last looked: saved in Orca, made by PipSpool or by another app. Put them into groups or hide them; a preset put away stops being new.",
                  "Профили, появившиеся с прошлого раза: сохранённые в Orca, созданные PipSpool или другой программой. Разложи их по группам или скрой — разложенный профиль перестаёт быть новым."),
    "empty.new_title": ("Nothing new", "Новых нет"),
    "empty.new": ("Presets that appear later, after a save in Orca or from PipSpool, show up here.",
                  "Здесь появятся профили, которые возникнут позже: после сохранения в Orca или из PipSpool."),
    "empty.fav_title": ("No favourites yet", "Избранного пока нет"),
    "empty.fav": ("Press the star on a preset to keep it at hand.", "Нажми звёздочку у профиля, чтобы держать его под рукой."),
    "empty.group_rule": ("Nothing matches the group's rule for this filter yet.", "По этому фильтру под правило группы пока ничего не подходит."),
    "btn.fav": ("Add to favourites", "В избранное"),
    "btn.unfav": ("Remove from favourites", "Убрать из избранного"),
    "msg.fav": ("Added to favourites", "Добавлен в избранное"),
    "msg.unfav": ("Removed from favourites", "Убран из избранного"),
    "menu.note": ("Note", "Заметка"),
    "drawer.note": ("Note", "Заметка"),
    "drawer.note_ph_filament": ("For example: dry 4 h at 65 °C, spool on the top shelf", "Например: сушить 4 ч при 65 °C, катушка на верхней полке"),
    "drawer.note_ph_printer": ("For example: new hotend since May", "Например: новый хотэнд с мая"),
    "drawer.note_ph_process": ("For example: for carriages, watch the first layer", "Например: для кареток, следить за первым слоем"),
    "drawer.note_hint": ("Kept in the plugin only; Orca does not see it.", "Хранится только в плагине, Orca её не видит."),
    "drawer.renamed": ("Orca renamed the base preset; it is now “{parent}”.", "Orca переименовала базовый профиль, теперь он называется «{parent}»."),
    "issue.orphan": ("No base preset", "Нет базового профиля"),
    "issue.no_printer": ("No printer", "Нет принтера"),
    "health.orphan": ("Orca no longer has the base preset. The preset still works with the settings it saved, but changes to the base no longer reach it; save it again on top of an existing preset to fix it.",
                      "В Orca больше нет базового профиля. Профиль работает с сохранёнными в нём настройками, но изменения базового до него не доходят; чтобы исправить, пересохрани его поверх существующего профиля."),
    "health.no_printer": ("None of the printers the preset is made for is set up in Orca now, so Orca offers it for no printer. Add the printer back or save the preset for a printer you have.",
                          "Ни одного принтера, для которого сделан профиль, сейчас нет в Orca, поэтому Orca его нигде не предлагает. Верни принтер или пересохрани профиль для имеющегося."),
    "health.orphan_row": ("Base “{parent}” is gone", "Нет базового «{parent}»"),
    "health.no_printer_row": ("Made for {printers}", "Сделан для: {printers}"),
    "health.ok_title": ("All presets are fine", "С профилями всё в порядке"),
    "health.ok": ("Every preset has its base preset and a printer to work with.", "У каждого профиля есть базовый профиль и принтер, для которого он сделан."),
    "rule.title": ("Fill automatically", "Заполнять автоматически"),
    "rule.text": ("Matching presets go into the group by themselves, new ones too. With several fields all must match; commas mean “any of”. A preset taken out by hand is not put back.",
                  "Подходящие профили попадают в группу сами, новые тоже. Если заполнено несколько полей, должны совпасть все; через запятую — любое из. Убранный вручную профиль правило не вернёт."),
    "rule.badge": ("Fills itself by a rule", "Заполняется по правилу"),
    "rule.match": ("{n} preset matches|{n} presets match", "Подходит {n} профиль|Подходят {n} профиля|Подходят {n} профилей"),
    "rule.none": ("Nothing matches yet", "Пока ничего не подходит"),
    "rf.type": ("Type", "Тип"),
    "rf.vendor": ("Vendor", "Производитель"),
    "rf.model": ("Printer model", "Модель принтера"),
    "rf.printer": ("Printer", "Принтер"),
    "rf.text": ("Name contains", "В названии есть"),
    "rf.any": ("any", "любой"),
    "btn.to_slots": ("To slots", "В слоты"),
    "menu.to_slots": ("Load into slots", "Загрузить в слоты"),
    "slots.title": ("Load into slots", "Загрузить в слоты"),
    "slots.text": ("Pick a filament for each slot of the current printer. Slots left as they are do not change.",
                   "Выбери филамент для каждого слота текущего принтера. Слоты «как есть» не меняются."),
    "slots.keep": ("Leave as it is", "Оставить как есть"),
    "slots.apply": ("Load", "Загрузить"),
    "slots.count": ("{n} slot will change|{n} slots will change", "Изменится {n} слот|Изменятся {n} слота|Изменятся {n} слотов"),
    "slots.none": ("Nothing to change", "Менять нечего"),
    "slots.extra": ("Did not fit: {n}; the printer has {slots} slots", "Не поместились: {n}, у принтера слотов: {slots}"),
    "slots.off": ("For another printer: {n}", "Для другого принтера: {n}"),
    "msg.applied_slots": ("Slots filled: {n}", "Заполнено слотов: {n}"),
    "err.slot": ("There is no slot {slot}: the printer has {n}.", "Слота {slot} нет: у принтера их {n}."),
    "btn.compare": ("Compare", "Сравнить"),
    "menu.compare_with": ("Compare with…", "Сравнить с…"),
    "cmp.title": ("Comparison", "Сравнение"),
    "cmp.pick": ("Pick a preset to compare with “{name}”.", "Выбери профиль для сравнения с «{name}»."),
    "cmp.loading": ("Comparing…", "Сравниваю…"),
    "cmp.filter": ("Filter settings and values", "Фильтр по параметрам и значениям"),
    "cmp.diff": ("{n} setting differs|{n} settings differ", "Отличается {n} параметр|Отличаются {n} параметра|Отличаются {n} параметров"),
    "cmp.same": ("same: {n}", "совпадают: {n}"),
    "cmp.none": ("No differences: the settings are the same", "Различий нет: настройки совпадают"),
    "cmp.truncated": ("the first 400 are shown", "показаны первые 400"),
    "cmp.too_many": ("Select two to four presets", "Выбери от двух до четырёх профилей"),
    "set.theme": ("Theme", "Тема"),
    "theme.auto": ("As in Orca", "Как в Orca"),
    "theme.warm": ("Warm", "Тёплая"),
    "theme.night": ("Dark", "Тёмная"),
    "set.favorites_first": ("Favourites on top", "Избранное сверху"),
    "set.backup": ("Backup", "Резервная копия"),
    "io.export": ("Export settings", "Экспорт настроек"),
    "io.export_text": ("Groups with their rules, favourites, notes, hidden presets and dismissed look-alikes. Keep the file, or move it to another computer or account.",
                       "Группы с правилами, избранное, заметки, скрытые профили и отклонённые похожие. Сохрани файл или перенеси на другой компьютер или в другую учётную запись."),
    "io.copy": ("Copy", "Скопировать"),
    "io.copied": ("Copied", "Скопировано"),
    "io.copy_failed": ("Copying did not work: select the text and press Ctrl+C.", "Скопировать не получилось: выдели текст и нажми Ctrl+C."),
    "io.save": ("Save file", "Сохранить файл"),
    "io.save_failed": ("The file could not be saved here; copy the text instead.", "Файл здесь сохранить не получилось, скопируй текст."),
    "io.import": ("Import settings", "Импорт настроек"),
    "io.import_text": ("Pick a file exported from Preset Groups or paste its text. Presets are matched by name.",
                       "Выбери файл, экспортированный из «Групп профилей», или вставь его текст. Профили сопоставляются по названию."),
    "io.pick": ("Choose file", "Выбрать файл"),
    "io.paste_ph": ("…or paste the exported text here", "…или вставь сюда экспортированный текст"),
    "io.merge": ("Add to mine", "Добавить к моим"),
    "io.replace": ("Replace mine", "Заменить мои"),
    "io.bad": ("This is not a Preset Groups export", "Это не экспорт «Групп профилей»"),
    "io.s_groups": ("Groups: {n}", "Групп: {n}"),
    "io.s_fav": ("Favourites: {n}", "Избранных: {n}"),
    "io.s_notes": ("Notes: {n}", "Заметок: {n}"),
    "io.s_hidden": ("Hidden: {n}", "Скрытых: {n}"),
    "msg.imported": ("Settings imported", "Настройки импортированы"),
}

_LANG = "en"


def _set_language(choice):
    """Select the UI language: "en", "ru" or "auto" (Orca's own language)."""
    global _LANG
    if choice not in LANGUAGES:
        try:
            choice = str(orca.host.app_info().get("language", ""))
        except Exception:
            choice = ""
        choice = "ru" if choice.lower().startswith("ru") else "en"
    _LANG = choice
    return _LANG


def _t(key, **values):
    text = STRINGS[key][LANGUAGES.index(_LANG)]
    return text.format(**values) if values else text


def _ui_strings():
    column = LANGUAGES.index(_LANG)
    return {key: value[column] for key, value in STRINGS.items()}


PAGE = r"""BUILD:PAGE"""


def _page():
    if PAGE != "BUILD:" + "PAGE":
        return PAGE
    # Not built: read the page next to this file (development only).
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "page.html"), encoding="utf-8") as stream:
        return stream.read()


def _collection(bundle, kind):
    return {"filament": bundle.filaments, "printer": bundle.printers, "process": bundle.prints}[kind]


def _values(preset):
    values = {}
    for key in preset.config_keys():
        value = preset.config_value(key)
        if value is not None:
            values[str(key)] = str(value)
    return values


def _label(preset):
    """The name Orca's own lists show: the alias when the preset has one."""
    alias = str(getattr(preset, "alias", "") or "")
    return alias or str(preset.name)


def _known_printers(bundle):
    """Names of the printer presets the user has: their own and the system ones they picked."""
    known = set()
    printers = bundle.printers
    for index in range(printers.size()):
        preset = printers.preset(index)
        if getattr(preset, "is_default", False) or not getattr(preset, "is_visible", True):
            continue
        known.update({str(preset.name), _label(preset)})
    return known


def read_presets(bundle, dismissed=None):
    """Every user preset of each kind, the look-alikes among them, the filament slots and the
    printers a filament can be made for."""
    dismissed = dismissed or {}
    data = {"kinds": {}, "duplicates": {}, "printers": [], "slots": [], "printer": "", "version": VERSION}
    printer = bundle.current_printer_preset()
    data["printer"] = _label(printer) if printer is not None else ""
    slot_names = [str(n) for n in bundle.current_filament_preset_names()]
    colours = split_values(bundle.full_config_value("filament_colour"))
    filaments = bundle.filaments
    for index, name in enumerate(slot_names):
        found = filaments.find_preset(name)
        data["slots"].append({"slot": index + 1, "name": name, "label": _label(found) if found is not None else name,
                              "color": colours[index] if index < len(colours) else ""})
    active = {
        "printer": str(printer.name) if printer is not None else "",
        "process": str(bundle.current_process_preset().name),
    }
    known = _known_printers(bundle)
    printers = set()
    for kind in KINDS:
        collection = _collection(bundle, kind)
        parents = {}
        records, values_by_name = [], {}
        for index in range(collection.size()):
            preset = collection.preset(index)
            if not preset.is_user():
                continue
            name = str(preset.name)
            values = _values(preset)
            parent_name = values.get("inherits", "")
            if parent_name and parent_name not in parents:
                parent = collection.find_preset(parent_name)
                parents[parent_name] = (str(parent.name), _values(parent)) if parent is not None else ("", {})
            parent_now, parent_values = parents.get(parent_name, ("", {}))
            if kind == "printer":
                own, inherited = [parent_name or name], []
            else:
                own = split_values(values.get("compatible_printers"))
                inherited = split_values(parent_values.get("compatible_printers"))
            if kind == "filament":
                selected = [i + 1 for i, slot in enumerate(slot_names) if slot == name]
            else:
                selected = [1] if active.get(kind) == name else []
            record = build_record(kind, name, _label(preset), values, parent_name, parent_values, own, inherited,
                                  bool(preset.is_compatible), selected, parent_now, known)
            if kind != "printer":
                printers.update(record["printers"])
            records.append(record)
            values_by_name[name] = values
        clusters = find_duplicates(kind, records, values_by_name, dismissed.get(kind, ()))
        for cluster in clusters:
            if cluster["keys"]:
                cluster["values"] = {key: {n: values_by_name[n].get(key, "") for n in cluster["names"]} for key in cluster["keys"]}
        data["kinds"][kind] = records
        data["duplicates"][kind] = clusters
    data["printers"] = sorted(printers, key=str.casefold)
    return data


def compare(bundle, kind, names):
    """The settings in which two to four presets of one kind differ."""
    collection = _collection(bundle, kind)
    values_by_name = {}
    for name in names:
        preset = collection.find_preset(name)
        if preset is None:
            raise ValueError(_t("err.not_found", name=name))
        values_by_name[name] = _values(preset)
    return compare_presets(names, values_by_name)


def apply_preset(kind, name, slot=None):
    """Select a preset in Orca: a filament for one slot, or the printer or process."""
    bundle = orca.host.preset_bundle()
    collection = _collection(bundle, kind)
    if collection.find_preset(name) is None:
        raise ValueError(_t("err.not_found", name=name))
    edited = collection.get_edited_preset()
    # Selecting another preset while the edited one has unsaved changes opens Orca's
    # "unsaved changes" dialog; ask for a save first instead of opening it from the page.
    if edited is not None and edited.is_dirty and str(edited.name) != name:
        raise ValueError(_t("err.dirty", name=_label(edited)))
    if kind == "filament":
        slots = len(bundle.current_filament_preset_names())
        if not 1 <= int(slot) <= slots:
            raise ValueError(_t("err.slot", slot=int(slot), n=slots))
    try:
        if kind == "filament":
            orca.host.preset.filament.begin_update(int(slot), name)
        else:
            getattr(orca.host.preset, kind).begin_update(preset_name=name)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(_t("err.apply", error=str(exc)[:200]))


def apply_slots(items):
    """Put several filaments into their slots, in slot order; stops at the first failure.
    Returns how many slots were filled."""
    done = 0
    for item in sorted(items, key=lambda i: int(i["slot"])):
        apply_preset("filament", str(item["name"]), int(item["slot"]))
        done += 1
    return done


class PresetGroupsPage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Preset Groups"

    def get_icon(self):
        icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presetgroups.svg")
        return icon if os.path.isfile(icon) else ""

    def get_ui(self):
        return _page()

    def get_default_config(self):
        return json.loads(json.dumps(DEFAULT_CONFIG))

    def _config(self):
        try:
            value = json.loads(self.get_config())
        except Exception:
            value = {}
        return clean_config(value)

    def _send_data(self, config, kind="data"):
        message = {"type": kind, "config": config,
                   "data": read_presets(orca.host.preset_bundle(), config.get("not_duplicates"))}
        if kind == "init":
            message.update({"strings": _ui_strings(), "language": _LANG})
        self.post_message(message)

    def on_message(self, data):
        try:
            kind = data.get("type")
            config = self._config()
            _set_language(config.get("language", "auto"))
            if kind == "init":
                self._send_data(config, "init")
            elif kind == "refresh":
                self._send_data(config)
            elif kind == "save_config":
                config = clean_config(data.get("config"))
                self.save_config(json.dumps(config, ensure_ascii=False))
                if data.get("reload"):
                    _set_language(config["language"])
                    self._send_data(config, "init")
                elif data.get("refresh"):
                    self._send_data(config)
            elif kind == "apply":
                preset_kind = data.get("kind")
                if preset_kind not in KINDS:
                    return
                name = str(data.get("name", ""))
                apply_preset(preset_kind, name, data.get("slot"))
                found = _collection(orca.host.preset_bundle(), preset_kind).find_preset(name)
                label = _label(found) if found is not None else name
                self._send_data(config)
                if preset_kind == "filament":
                    self.post_message({"type": "notice", "message": _t("msg.applied_slot", name=label, slot=int(data.get("slot")))})
                else:
                    self.post_message({"type": "notice", "message": _t("msg.applied", name=label)})
            elif kind == "apply_slots":
                items = [i for i in data.get("items", []) if isinstance(i, dict) and i.get("name")][:32]
                try:
                    done = apply_slots(items)
                finally:
                    self._send_data(config)
                self.post_message({"type": "notice", "message": _t("msg.applied_slots", n=done)})
            elif kind == "compare":
                preset_kind = data.get("kind")
                names = [str(n) for n in data.get("names", [])][:4]
                if preset_kind not in KINDS or len(names) < 2:
                    return
                result = compare(orca.host.preset_bundle(), preset_kind, names)
                self.post_message({"type": "compare", "kind": preset_kind, "names": names, **result})
        except Exception as exc:
            self.post_message({"type": "error", "message": str(exc)[:300]})


@orca.plugin
class PresetGroupsPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(PresetGroupsPage)
