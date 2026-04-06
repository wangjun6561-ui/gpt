import 'package:isar/isar.dart';

part 'box.g.dart';

@collection
class BoxModel {
  Id id = Isar.autoIncrement;

  late String name;
  late String color;
  late String icon;
  late int sortOrder;
  String? description;
  late bool isDefault;
  late DateTime createdAt;

  BoxModel();
}
