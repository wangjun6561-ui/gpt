import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/box.dart';
import '../services/isar_service.dart';

final boxesProvider = FutureProvider<List<BoxModel>>((ref) async {
  final isar = IsarService.instance.isar;
  return isar.boxModels.where().sortBySortOrder().findAll();
});
