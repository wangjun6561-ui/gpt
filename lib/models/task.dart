import 'package:isar/isar.dart';

part 'task.g.dart';

@collection
class TaskModel {
  Id id = Isar.autoIncrement;

  late int boxId;
  late String content;
  late bool isCompleted;
  late int sortOrder;
  int priority = 1;
  DateTime? dueDate;
  DateTime? completedAt;
  late DateTime createdAt;

  TaskModel();
}
