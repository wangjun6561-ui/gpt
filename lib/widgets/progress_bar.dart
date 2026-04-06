import 'package:flutter/material.dart';

class ProgressBar extends StatelessWidget {
  const ProgressBar({
    super.key,
    required this.progress,
    required this.color,
  });

  final double progress;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(100),
      child: LinearProgressIndicator(
        minHeight: 8,
        value: progress,
        backgroundColor: Colors.white.withValues(alpha: 0.2),
        valueColor: AlwaysStoppedAnimation<Color>(color),
      ),
    );
  }
}
