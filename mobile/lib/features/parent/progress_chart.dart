import 'package:flutter/material.dart';

import '../../app/format.dart';
import '../../app/theme.dart';
import '../../models/parent.dart';

/// Note moyenne de chaque semaine (une seule série, une seule couleur) : barres fines
/// posées sur la ligne de base, valeur écrite seulement pour la semaine en cours.
/// Chaque barre a sa description pour les lecteurs d'écran, et une infobulle au toucher.
class ProgressChart extends StatelessWidget {
  const ProgressChart({required this.weeks, super.key});

  final List<WeekStats> weeks;

  static const _height = 96.0;

  static String describe(WeekStats w) {
    final day = w.weekStart;
    final sessions = '${w.sessions} séance${w.sessions > 1 ? 's' : ''}';
    final average = w.averageScore == null ? '' : ', ${score(w.averageScore!)} / 10 en moyenne';
    return 'Semaine du ${day.day}/${day.month} : $sessions, ${w.minutes} min$average';
  }

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.black54);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: _height + 22,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (final (i, w) in weeks.indexed)
                Expanded(
                  child: Tooltip(
                    message: describe(w),
                    triggerMode: TooltipTriggerMode.tap,
                    child: Semantics(
                      label: describe(w),
                      excludeSemantics: true,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 6),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            if (i == weeks.length - 1 && w.averageScore != null)
                              Text(
                                score(w.averageScore!),
                                style: const TextStyle(fontWeight: FontWeight.w700),
                              ),
                            const SizedBox(height: 4),
                            Container(
                              height: w.averageScore == null
                                  ? 2
                                  : (w.averageScore! / 10 * _height).clamp(4, _height),
                              constraints: const BoxConstraints(maxWidth: 28),
                              decoration: BoxDecoration(
                                color: w.averageScore == null ? Colors.black12 : LudiColors.primary,
                                borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        const Divider(height: 1, color: Colors.black26),
        const SizedBox(height: 4),
        Row(
          children: [
            for (final w in weeks)
              Expanded(
                child: Text(
                  '${w.weekStart.day}/${w.weekStart.month}',
                  textAlign: TextAlign.center,
                  style: muted,
                ),
              ),
          ],
        ),
      ],
    );
  }
}
