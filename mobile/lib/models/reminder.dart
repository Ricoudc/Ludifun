import 'account.dart' show Json;

/// Un rappel du jour (§48) : au plus un par enfant, calculé par le serveur.
class ParentReminder {
  const ParentReminder({required this.childId, required this.childName, required this.text});

  factory ParentReminder.fromJson(Json json) => ParentReminder(
    childId: json['child_id'] as String,
    childName: json['child_name'] as String,
    text: json['text'] as String,
  );

  final String childId;
  final String childName;
  final String text;
}
