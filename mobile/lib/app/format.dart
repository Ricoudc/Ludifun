import '../models/lesson.dart';

const _weekdays = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'];
const _months = [
  'janvier',
  'février',
  'mars',
  'avril',
  'mai',
  'juin',
  'juillet',
  'août',
  'septembre',
  'octobre',
  'novembre',
  'décembre',
];

/// « jeudi », « demain », « le 12 octobre » : quand revoir la leçon, à l'heure du téléphone.
String dayLabel(DateTime moment, DateTime now) {
  final day = DateUtils.dateOnly(moment.toLocal());
  final today = DateUtils.dateOnly(now.toLocal());
  final days = day.difference(today).inDays;
  return switch (days) {
    <= 0 => 'aujourd\'hui',
    1 => 'demain',
    < 7 => _weekdays[day.weekday - 1],
    _ => 'le ${day.day == 1 ? '1er' : day.day} ${_months[day.month - 1]}',
  };
}

/// État de révision d'une leçon de l'accueil (écran 1).
String reviewLabel(LessonSummary lesson, DateTime now) {
  if (lesson.due) return 'à revoir aujourd\'hui 🔄';
  if (lesson.mastered) return 'maîtrisée ✓';
  final next = lesson.nextReviewAt;
  return next == null ? 'à réviser' : 'à revoir ${dayLabel(next, now)}';
}

abstract final class DateUtils {
  static DateTime dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);
}
