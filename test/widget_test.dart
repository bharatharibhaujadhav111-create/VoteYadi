import 'package:flutter_test/flutter_test.dart';
import 'package:voter_finder/core/models/models.dart';

void main() {
  test('Duplicate overview keeps the cross-village sections separate', () {
    final overview = DuplicateOverview.fromJson({
      'epic': [],
      'name': [],
      'same_relative': [
        {
          'key': 'name:relative',
          'label': 'Person',
          'relation_label': 'Relative',
          'records': [
            {
              'id': 1,
              'name': 'Person',
              'relation_name': 'Relative',
              'village': 'A',
            },
            {
              'id': 2,
              'name': 'Person',
              'relation_name': 'Relative',
              'village': 'B',
            },
          ],
        },
      ],
      'different_relative': [
        {
          'key': 'name',
          'label': 'Person',
          'relation_label': '',
          'records': [
            {
              'id': 1,
              'name': 'Person',
              'relation_name': 'Relative',
              'village': 'A',
            },
            {
              'id': 3,
              'name': 'Person',
              'relation_name': 'Other',
              'village': 'B',
            },
          ],
        },
      ],
    });
    expect(overview.sameRelativeAcrossVillages.single.records.length, 2);
    expect(
      overview.differentRelativeAcrossVillages.single.records.last.relationName,
      'Other',
    );
    expect(overview.crossVillageSetupRequired, isFalse);
  });

  test('SearchResponse parses and paginates', () {
    final r = SearchResponse.fromJson({
      'results': [
        {
          'id': 1,
          'name': 'Vijay Bharat Jadhav',
          'relation_name': 'Bharat Jadhav',
          'page': 3,
          'pdf': 'Tirhe/Part_101.pdf',
          'pdf_name': 'Part_101.pdf',
          'village': 'Tirhe',
        },
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
