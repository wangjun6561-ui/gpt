import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/box.dart';
import '../models/settings.dart';
import '../models/task.dart';
import '../utils/constants.dart';

class IsarService {
  IsarService._();

  static final IsarService instance = IsarService._();
  static const String _legacyExportFileName = 'taskbox_legacy_export.json';
  late final Database db;

  Future<void> initialize() async {
    if (_isInitialized) return;

    final databasesPath = await getDatabasesPath();
    final path = p.join(databasesPath, 'taskbox.db');
    db = await openDatabase(
      path,
      version: 1,
      onCreate: (database, version) async {
        await database.execute('''
          CREATE TABLE boxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            icon TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            description TEXT,
            is_default INTEGER NOT NULL,
            created_at TEXT NOT NULL
          )
        ''');

        await database.execute('''
          CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            box_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            is_completed INTEGER NOT NULL,
            sort_order INTEGER NOT NULL,
            priority INTEGER NOT NULL DEFAULT 1,
            due_date TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL
          )
        ''');

        await database.execute('''
          CREATE TABLE settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deepseek_api_key TEXT NOT NULL DEFAULT '',
            theme_mode TEXT NOT NULL DEFAULT 'system'
          )
        ''');
      },
    );

    final migrated = await _migrateFromLegacyIsarIfNeeded();
    if (!migrated) {
      await _seedDataIfNeeded();
    }
  }

  bool get _isInitialized {
    try {
      return db.isOpen;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _migrateFromLegacyIsarIfNeeded() async {
    final countResult = await db.rawQuery('SELECT COUNT(*) AS c FROM boxes');
    final hasBoxes = (countResult.first['c'] as int) > 0;
    if (hasBoxes) return false;

    final databasesPath = await getDatabasesPath();
    final hasLegacyIsarFiles = await _hasLegacyIsarFiles(databasesPath);
    if (!hasLegacyIsarFiles) return false;

    final exportFile = File(p.join(databasesPath, _legacyExportFileName));
    if (!await exportFile.exists()) {
      // Legacy Isar data exists. Avoid seeding defaults so we never overwrite old user data
      // before migration data is exported on a later version.
      await _ensureSettingsRow();
      return true;
    }

    final raw = await exportFile.readAsString();
    final payload = jsonDecode(raw) as Map<String, dynamic>;

    await db.transaction((txn) async {
      final boxes = (payload['boxes'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>();
      for (final box in boxes) {
        await txn.insert('boxes', {
          'id': box['id'] as int?,
          'name': box['name'] as String? ?? '',
          'color': box['color'] as String? ?? '',
          'icon': box['icon'] as String? ?? '',
          'sort_order': box['sort_order'] as int? ?? 0,
          'description': box['description'] as String?,
          'is_default': (box['is_default'] as bool? ?? false) ? 1 : (box['is_default'] as int? ?? 0),
          'created_at': box['created_at'] as String? ?? DateTime.now().toIso8601String(),
        });
      }

      final tasks = (payload['tasks'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>();
      for (final task in tasks) {
        await txn.insert('tasks', {
          'id': task['id'] as int?,
          'box_id': task['box_id'] as int? ?? 0,
          'content': task['content'] as String? ?? '',
          'is_completed': (task['is_completed'] as bool? ?? false)
              ? 1
              : (task['is_completed'] as int? ?? 0),
          'sort_order': task['sort_order'] as int? ?? 0,
          'priority': task['priority'] as int? ?? 1,
          'due_date': task['due_date'] as String?,
          'completed_at': task['completed_at'] as String?,
          'created_at': task['created_at'] as String? ?? DateTime.now().toIso8601String(),
        });
      }

      final settings = payload['settings'] as Map<String, dynamic>?;
      if (settings == null) {
        await txn.insert('settings', SettingsModel().toMap()..remove('id'));
      } else {
        await txn.insert('settings', {
          'id': settings['id'] as int?,
          'deepseek_api_key': settings['deepseek_api_key'] as String? ?? '',
          'theme_mode': settings['theme_mode'] as String? ?? 'system',
        });
      }
    });

    return true;
  }

  Future<bool> _hasLegacyIsarFiles(String databasesPath) async {
    final directory = Directory(databasesPath);
    if (!await directory.exists()) return false;

    await for (final entity in directory.list(followLinks: false)) {
      if (entity is File && p.extension(entity.path).toLowerCase() == '.isar') {
        return true;
      }
    }
    return false;
  }

  Future<void> _ensureSettingsRow() async {
    final rows = await db.rawQuery('SELECT COUNT(*) AS c FROM settings');
    if ((rows.first['c'] as int) == 0) {
      await db.insert('settings', SettingsModel().toMap()..remove('id'));
    }
  }

  Future<void> _seedDataIfNeeded() async {
    final countResult = await db.rawQuery('SELECT COUNT(*) AS c FROM boxes');
    final hasBoxes = (countResult.first['c'] as int) > 0;
    if (hasBoxes) return;

    final boxes = AppConstants.defaultBoxes();
    final boxIdByName = <String, int>{};

    await db.transaction((txn) async {
      for (final box in boxes) {
        final id = await txn.insert('boxes', box.toMap()..remove('id'));
        box.id = id;
        boxIdByName[box.name] = id;
      }

      final tasks = AppConstants.defaultTasks(
        relaxBoxId: boxIdByName['放松盒']!,
        rewardBoxId: boxIdByName['奖励盒']!,
        punishBoxId: boxIdByName['惩罚盒']!,
        miscBoxId: boxIdByName['杂事盒']!,
      );

      for (final task in tasks) {
        final id = await txn.insert('tasks', task.toMap()..remove('id'));
        task.id = id;
      }

      await txn.insert('settings', SettingsModel().toMap()..remove('id'));
    });
  }

  Future<List<BoxModel>> getBoxes() async {
    final rows = await db.query('boxes', orderBy: 'sort_order ASC');
    return rows.map(BoxModel.fromMap).toList();
  }

  Future<BoxModel?> getBoxByName(String name) async {
    final rows = await db.query('boxes', where: 'name = ?', whereArgs: [name], limit: 1);
    if (rows.isEmpty) return null;
    return BoxModel.fromMap(rows.first);
  }

  Future<List<TaskModel>> getTasksByBoxId(int boxId, {bool? isCompleted}) async {
    final whereParts = <String>['box_id = ?'];
    final whereArgs = <Object?>[boxId];
    if (isCompleted != null) {
      whereParts.add('is_completed = ?');
      whereArgs.add(isCompleted ? 1 : 0);
    }

    final rows = await db.query(
      'tasks',
      where: whereParts.join(' AND '),
      whereArgs: whereArgs,
      orderBy: 'sort_order ASC',
    );
    return rows.map(TaskModel.fromMap).toList();
  }

  Future<int> countTasksByBoxId(int boxId) async {
    final rows = await db.rawQuery('SELECT COUNT(*) AS c FROM tasks WHERE box_id = ?', [boxId]);
    return rows.first['c'] as int;
  }

  Future<void> insertTask(TaskModel task) async {
    final id = await db.insert('tasks', task.toMap()..remove('id'));
    task.id = id;
  }

  Future<void> updateTask(TaskModel task) async {
    await db.update(
      'tasks',
      task.toMap()..remove('id'),
      where: 'id = ?',
      whereArgs: [task.id],
    );
  }

  Future<SettingsModel> getSettings() async {
    final rows = await db.query('settings', limit: 1);
    if (rows.isNotEmpty) return SettingsModel.fromMap(rows.first);

    final setting = SettingsModel();
    final id = await db.insert('settings', setting.toMap()..remove('id'));
    setting.id = id;
    return setting;
  }

  Future<void> updateSettings(SettingsModel settings) async {
    await db.update(
      'settings',
      settings.toMap()..remove('id'),
      where: 'id = ?',
      whereArgs: [settings.id],
    );
  }
}
