import '../models/box.dart';
import '../models/task.dart';

class AppConstants {
  static const importantColor = '#FF6B6B';
  static const relaxColor = '#4ECDC4';
  static const rewardColor = '#FFD93D';
  static const punishColor = '#6C757D';
  static const miscColor = '#A29BFE';

  static List<BoxModel> defaultBoxes() {
    final now = DateTime.now();
    return [
      BoxModel()
        ..name = '重要事项'
        ..color = importantColor
        ..icon = 'star'
        ..sortOrder = 0
        ..isDefault = true
        ..description = '放这里的，都是不做会后悔的事。别拖了，一件一件来。'
        ..createdAt = now,
      BoxModel()
        ..name = '放松盒'
        ..color = relaxColor
        ..icon = 'coffee'
        ..sortOrder = 1
        ..isDefault = true
        ..description = '累了就来这里抽一个，给自己一个正当的休息理由。'
        ..createdAt = now,
      BoxModel()
        ..name = '奖励盒'
        ..color = rewardColor
        ..icon = 'gift'
        ..sortOrder = 2
        ..isDefault = true
        ..description = '完成了重要任务？来这里随机抽一个奖励犒劳自己吧。'
        ..createdAt = now,
      BoxModel()
        ..name = '惩罚盒'
        ..color = punishColor
        ..icon = 'bolt'
        ..sortOrder = 3
        ..isDefault = true
        ..description = '没完成计划？随机抽一个惩罚，对自己狠一点才能进步。'
        ..createdAt = now,
      BoxModel()
        ..name = '杂事盒'
        ..color = miscColor
        ..icon = 'inbox'
        ..sortOrder = 4
        ..isDefault = false
        ..description = '日常琐事集中放这里，清空它会很有成就感。'
        ..createdAt = now,
    ];
  }

  static List<TaskModel> defaultTasks({
    required int relaxBoxId,
    required int rewardBoxId,
    required int punishBoxId,
    required int miscBoxId,
  }) {
    final now = DateTime.now();
    TaskModel create(int boxId, String content, int sortOrder) => TaskModel()
      ..boxId = boxId
      ..content = content
      ..isCompleted = false
      ..sortOrder = sortOrder
      ..createdAt = now;

    return [
      create(relaxBoxId, '听音乐两首', 0),
      create(relaxBoxId, '冥想 5min', 1),
      create(relaxBoxId, '靠墙站立', 2),
      create(relaxBoxId, '洗袜子/衣服/扫地', 3),
      create(relaxBoxId, '整理桌面', 4),
      create(rewardBoxId, '高分牛肉火锅', 0),
      create(rewardBoxId, '高分自助餐', 1),
      create(punishBoxId, '复盘 1k 字', 0),
      create(punishBoxId, '输出主题文章 2k 字', 1),
      create(miscBoxId, '购买 xx', 0),
    ];
  }
}
