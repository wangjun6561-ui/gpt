import 'package:flutter/material.dart';

class TodayOverviewCard extends StatelessWidget {
  const TodayOverviewCard({super.key, required this.total, required this.done});

  final int total;
  final int done;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(colors: [Color(0xFF6C5CE7), Color(0xFFA29BFE)]),
      ),
      child: Text(
        '今日共 $total 项任务 · 已完成 $done 项',
        style: const TextStyle(
          color: Colors.white,
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
