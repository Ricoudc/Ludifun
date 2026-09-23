import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';

import 'models.dart';

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);

  @override
  String toString() => message;
}

class ApiClient {
  // Émulateur Android → machine hôte. À surcharger avec --dart-define=API_URL=...
  static const baseUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

  final http.Client _http;
  ApiClient([http.Client? client]) : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  dynamic _decode(http.Response r) {
    final body = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 400) {
      final detail = body is Map && body['detail'] is String ? body['detail'] : 'Erreur ${r.statusCode}';
      throw ApiException(r.statusCode, detail);
    }
    return body;
  }

  Future<dynamic> _post(String path, [Object? json]) async => _decode(await _http.post(
        _uri(path),
        headers: {'content-type': 'application/json'},
        body: json == null ? null : jsonEncode(json),
      ));

  Future<dynamic> _get(String path) async => _decode(await _http.get(_uri(path)));

  Future<Child> createChild(String name, String grade) async =>
      Child.fromJson(await _post('/children', {'display_name': name, 'grade': grade}));

  Future<Child> getChild(int id) async => Child.fromJson(await _get('/children/$id'));

  Future<List<LessonSummary>> listLessons(int childId) async =>
      (await _get('/children/$childId/lessons') as List).map((j) => LessonSummary.fromJson(j)).toList();

  Future<Lesson> getLesson(int id) async => Lesson.fromJson(await _get('/lessons/$id'));

  /// Envoie les photos de la leçon. Elles ne sont pas conservées par le serveur.
  Future<Lesson> createLesson(int childId, List<XFile> photos, {String? text}) async {
    final req = http.MultipartRequest('POST', _uri('/lessons'))..fields['child_id'] = '$childId';
    if (text != null && text.trim().isNotEmpty) req.fields['text'] = text;
    for (final photo in photos) {
      req.files.add(http.MultipartFile.fromBytes(
        'images',
        await photo.readAsBytes(),
        filename: photo.name,
        contentType: MediaType('image', photo.name.toLowerCase().endsWith('.png') ? 'png' : 'jpeg'),
      ));
    }
    final streamed = await _http.send(req);
    return Lesson.fromJson(_decode(await http.Response.fromStream(streamed)));
  }

  Future<RevisionSession> startSession(int lessonId, String mode) async =>
      RevisionSession.fromJson(await _post('/lessons/$lessonId/sessions', {'mode': mode}));

  Future<AnswerResult> answer(int sessionId, int questionId, String answer, int timeMs) async =>
      AnswerResult.fromJson(await _post('/sessions/$sessionId/answers',
          {'question_id': questionId, 'answer': answer, 'time_ms': timeMs}));

  Future<SessionReport> finish(int sessionId) async =>
      SessionReport.fromJson(await _post('/sessions/$sessionId/finish'));

  Future<ChildProgress> progress(int childId) async =>
      ChildProgress.fromJson(await _get('/children/$childId/progress'));
}
