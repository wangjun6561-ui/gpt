import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/box.dart';
import '../models/settings.dart';
import '../models/task.dart';
import '../utils/constants.dart';

class IsarService {
  IsarService._();

  static final IsarService instance = IsarService._();
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

    await _seedDataIfNeeded();
  }

  bool get _isInitialized {
    try {
      return db.isOpen;
    } catch (_) {
      return false;
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
