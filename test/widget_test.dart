import 'package:flutter_test/flutter_test.dart';
import 'package:voter_finder/core/models/models.dart';

void main() {
  test('SearchResponse parses and paginates', () {
    final r = SearchResponse.fromJson({
      'results': [
        {'id': 1, 'name': 'Vijay Bharat Jadhav', 'relation_name': 'Bharat Jadhav', 'page': 3, 'pdf': 'Tirhe/Part_101.pdf', 'pdf_name': 'Part_101.pdf', 'village': 'Tirhe'}
      ],
      'total': 25,
      'page': 1,
      'page_size': 10,
      'took_ms': 1.2,
      'query': {},
    });
    expect(r.results.single.village, 'Tirhe');
    expect(r.totalPages, 3);
  });
}
