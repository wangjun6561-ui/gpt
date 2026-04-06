import 'package:isar/isar.dart';
import 'package:path_provider/path_provider.dart';

import '../models/box.dart';
import '../models/settings.dart';
import '../models/task.dart';
import '../utils/constants.dart';

class IsarService {
  IsarService._();

  static final IsarService instance = IsarService._();
  late final Isar isar;

  Future<void> initialize() async {
    if (Isar.instanceNames.isNotEmpty) {
      isar = Isar.getInstance(Isar.instanceNames.first)!;
      return;
    }

    final dir = await getApplicationDocumentsDirectory();
    isar = await Isar.open(
      [BoxModelSchema, TaskModelSchema, SettingsModelSchema],
      directory: dir.path,
    );

    await _seedDataIfNeeded();
  }

  Future<void> _seedDataIfNeeded() async {
    final hasBoxes = await isar.boxModels.count() > 0;
    if (hasBoxes) return;

    final boxes = AppConstants.defaultBoxes();
    await isar.writeTxn(() async {
      await isar.boxModels.putAll(boxes);

      final relax = boxes.firstWhere((e) => e.name == '放松盒').id;
      final reward = boxes.firstWhere((e) => e.name == '奖励盒').id;
      final punish = boxes.firstWhere((e) => e.name == '惩罚盒').id;
      final misc = boxes.firstWhere((e) => e.name == '杂事盒').id;

      final tasks = AppConstants.defaultTasks(
        relaxBoxId: relax,
        rewardBoxId: reward,
        punishBoxId: punish,
        miscBoxId: misc,
      );
      await isar.taskModels.putAll(tasks);

      await isar.settingsModels.put(SettingsModel());
    });
  }
}
