import {defineArrayMember, defineField, defineType} from 'sanity'
import {artikelSeiten} from './artikelSeiten'

const FARBEN = [
  {title: 'Beige', value: '#f0e8dd'},
  {title: 'Lila', value: '#eacfff'},
  {title: 'Grün', value: '#b0dfae'},
  {title: 'Orange', value: '#ffcd91'},
]

/** Body text: paragraphs, sub-headings, quotes, lists, links – plus images with caption. */
const textBlock = defineArrayMember({
  type: 'block',
  styles: [
    {title: 'Absatz', value: 'normal'},
    {title: 'Zwischenüberschrift', value: 'h2'},
    {title: 'Zitat (hervorgehoben)', value: 'blockquote'},
  ],
  lists: [
    {title: 'Aufzählung', value: 'bullet'},
    {title: 'Nummeriert', value: 'number'},
  ],
  marks: {
    decorators: [
      {title: 'Fett', value: 'strong'},
      {title: 'Kursiv', value: 'em'},
    ],
    annotations: [
      {
        name: 'link',
        type: 'object',
        title: 'Link',
        fields: [{name: 'href', type: 'url', title: 'Adresse', validation: (r) => r.uri({scheme: ['http', 'https', 'mailto']})}],
      },
    ],
  },
})

export const artikel = defineType({
  name: 'artikel',
  title: 'Artikel',
  type: 'document',
  groups: [
    {name: 'kachel', title: 'Kachel auf der Startseite', default: true},
    {name: 'seite', title: 'Artikelseite'},
    {name: 'bezuege', title: 'Personen & Orte'},
  ],
  fields: [
    // ------------------------------------------------------------ basics
    defineField({name: 'titel', title: 'Titel', type: 'string', validation: (r) => r.required(), group: ['kachel', 'seite']}),
    defineField({name: 'autor', title: 'Autor:in(nen)', type: 'string', description: 'z. B. Gerhard Benetka & Clarissa Rudolph', group: ['kachel', 'seite']}),

    // ------------------------------------------------------------ card
    defineField({
      name: 'anzeige',
      title: 'Darstellung auf der Startseite',
      type: 'string',
      group: 'kachel',
      initialValue: 'normal',
      options: {
        layout: 'radio',
        list: [
          {title: 'Normale Kachel', value: 'normal'},
          {title: 'Hervorgehoben (große Kachel über die ganze Breite)', value: 'hervorgehoben'},
          {title: 'Nicht auf der Startseite zeigen', value: 'versteckt'},
        ],
      },
    }),
    defineField({
      name: 'reihenfolge',
      title: 'Reihenfolge',
      type: 'number',
      group: 'kachel',
      description: 'Position auf der Startseite (kleinere Zahl = weiter oben). Die bestehenden Artikel haben 10, 20, 30 … – eine 25 landet also dazwischen. Leer = am Ende.',
    }),
    defineField({
      name: 'kachelTitel',
      title: 'Titel auf der Kachel (optional)',
      type: 'string',
      group: 'kachel',
      description: 'Falls die Kachel einen kürzeren Titel zeigen soll als den Artikeltitel.',
    }),
    defineField({name: 'teaser', title: 'Kurztext auf der Kachel', type: 'text', rows: 3, group: 'kachel'}),
    defineField({
      name: 'kachelbild',
      title: 'Bild der Kachel',
      type: 'image',
      options: {hotspot: true},
      group: 'kachel',
      description: 'Hintergrundbild (wird abgedunkelt). Ohne Bild wird das Titelbild der Artikelseite verwendet.',
    }),

    // ------------------------------------------------------------ page
    defineField({
      name: 'seite',
      title: 'Bestehende Seite auf der Website',
      type: 'string',
      group: 'seite',
      options: {list: artikelSeiten},
      description: 'Nur für die 15 ursprünglichen Artikel. Für einen NEUEN Artikel leer lassen und unten den Inhalt eingeben.',
    }),
    defineField({
      name: 'slug',
      title: 'Web-Adresse (neuer Artikel)',
      type: 'slug',
      group: 'seite',
      options: {source: 'titel', maxLength: 80},
      description: 'Ergibt …/artikel/<adresse>/ – auf „Generate“ klicken.',
      hidden: ({document}) => Boolean(document?.seite),
      validation: (r) =>
        r.custom((value, ctx) => {
          const doc = ctx.document as {seite?: string; inhalt?: unknown[]}
          if (!doc?.seite && doc?.inhalt?.length && !value?.current) return 'Bitte eine Web-Adresse erzeugen.'
          return true
        }),
    }),
    defineField({
      name: 'farbe',
      title: 'Farbe der Artikelseite',
      type: 'string',
      group: 'seite',
      initialValue: '#f0e8dd',
      options: {list: FARBEN, layout: 'radio', direction: 'horizontal'},
      hidden: ({document}) => Boolean(document?.seite),
    }),
    defineField({
      name: 'titelbild',
      title: 'Titelbild (oben, ganze Breite)',
      type: 'image',
      options: {hotspot: true},
      group: 'seite',
      hidden: ({document}) => Boolean(document?.seite),
    }),
    defineField({
      name: 'untertitel',
      title: 'Einleitung unter dem Titel',
      type: 'text',
      rows: 4,
      group: 'seite',
      hidden: ({document}) => Boolean(document?.seite),
    }),
    defineField({
      name: 'autorInfo',
      title: 'Über die Autor:innen (Kasten links)',
      type: 'text',
      rows: 4,
      group: 'seite',
      hidden: ({document}) => Boolean(document?.seite),
    }),
    defineField({
      name: 'inhalt',
      title: 'Text',
      type: 'array',
      group: 'seite',
      hidden: ({document}) => Boolean(document?.seite),
      of: [
        textBlock,
        defineArrayMember({
          type: 'image',
          title: 'Bild',
          options: {hotspot: true},
          fields: [
            defineField({name: 'bildunterschrift', title: 'Bildunterschrift', type: 'text', rows: 2}),
            defineField({name: 'quelle', title: 'Quelle', type: 'string'}),
          ],
        }),
      ],
    }),
    defineField({
      name: 'bibliographie',
      title: 'Bibliographie',
      type: 'array',
      group: 'seite',
      description: 'Ein Absatz pro Eintrag. Erscheint als aufklappbarer Kasten neben dem Text.',
      hidden: ({document}) => Boolean(document?.seite),
      of: [defineArrayMember({type: 'block', styles: [{title: 'Eintrag', value: 'normal'}], lists: [], marks: {decorators: [{title: 'Kursiv', value: 'em'}], annotations: []}})],
    }),
    defineField({
      name: 'weiterlesen',
      title: 'Weiterlesen (optional)',
      type: 'array',
      group: 'seite',
      description: 'Bis zu 3 Artikel am Seitenende. Leer = die nächsten Artikel in der Reihenfolge der Startseite.',
      of: [{type: 'reference', to: [{type: 'artikel'}]}],
      validation: (r) => r.max(3),
    }),

    // ------------------------------------------------------------ relations
    defineField({
      name: 'personen',
      title: 'Personen',
      type: 'array',
      group: 'bezuege',
      description: 'Der Artikel erscheint auch auf der Karteikarte dieser Personen.',
      of: [{type: 'reference', to: [{type: 'person'}]}],
    }),
    defineField({
      name: 'orte',
      title: 'Orte',
      type: 'array',
      group: 'bezuege',
      description: 'Der Artikel erscheint auch bei diesen Orten auf der Karte.',
      of: [{type: 'reference', to: [{type: 'ort'}]}],
    }),
  ],
  orderings: [{title: 'Reihenfolge', name: 'reihenfolge', by: [{field: 'reihenfolge', direction: 'asc'}]}],
  preview: {
    select: {title: 'titel', subtitle: 'autor', anzeige: 'anzeige', media: 'kachelbild', seite: 'seite'},
    prepare: ({title, subtitle, anzeige, media, seite}) => ({
      title,
      subtitle: [anzeige === 'hervorgehoben' ? '★ hervorgehoben' : anzeige === 'versteckt' ? 'nicht auf Startseite' : null, seite ? 'bestehende Seite' : null, subtitle]
        .filter(Boolean)
        .join(' · '),
      media,
    }),
  },
})
