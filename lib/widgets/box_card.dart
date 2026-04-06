import 'package:flutter/material.dart';

import '../models/box.dart';
import 'progress_bar.dart';

class BoxCard extends StatelessWidget {
  const BoxCard({
    super.key,
    required this.box,
    required this.pending,
    required this.total,
    required this.onTap,
    required this.height,
  });

  final BoxModel box;
  final int pending;
  final int total;
  final VoidCallback onTap;
  final double height;

  @override
  Widget build(BuildContext context) {
    final start = _hex(box.color);
    final end = Color.lerp(start, Colors.white, 0.2)!;
    final progress = total == 0 ? 0.0 : (total - pending) / total;

    return InkWell(
      borderRadius: BorderRadius.circular(24),
      onTap: onTap,
      child: Container(
        height: height,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          gradient: LinearGradient(colors: [start, end]),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(box.name,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                  fontSize: 16,
                )),
            const Spacer(),
            Text('$pending',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w700)),
            Text('项待完成',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.85))),
            const SizedBox(height: 12),
            ProgressBar(progress: progress, color: Colors.white),
          ],
        ),
      ),
    );
  }

  Color _hex(String hex) {
    final value = hex.replaceAll('#', '');
    return Color(int.parse('FF$value', radix: 16));
  }
}
