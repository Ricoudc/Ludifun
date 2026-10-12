import 'account.dart' show Json;

/// Assistant parent (§46) : une question et sa réponse, calculée à partir des données réelles.
class AssistantAnswer {
  const AssistantAnswer({
    required this.question,
    required this.title,
    required this.lines,
    required this.basedOn,
  });

  factory AssistantAnswer.fromJson(Json json) => AssistantAnswer(
    question: json['question'] as String,
    title: json['title'] as String,
    lines: (json['lines'] as List<dynamic>).cast<String>(),
    basedOn: (json['based_on'] as List<dynamic>? ?? const []).cast<String>(),
  );

  /// `week`, `help`, `exam` ou `progress`.
  final String question;
  final String title;
  final List<String> lines;
  final List<String> basedOn;
}
