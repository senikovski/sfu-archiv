import {defineField, defineType} from 'sanity'

export const person = defineType({
  name: 'person',
  title: 'Person',
  type: 'document',
  fields: [
    defineField({name: 'name', title: 'Name', type: 'string', validation: (r) => r.required()}),
    defineField({
      name: 'jahre',
      title: 'Lebensdaten',
      type: 'string',
      description: 'z. B. 1879–1963',
    }),
    defineField({
      name: 'text',
      title: 'Kurztext',
      type: 'text',
      rows: 6,
      description: 'Erscheint auf der Karteikarte auf der Startseite.',
    }),
    defineField({
      name: 'portrait',
      title: 'Porträt',
      type: 'image',
      options: {hotspot: true},
      description: 'Hochformat. Ohne Bild wird ein Platzhalter gezeigt.',
    }),
    defineField({
      name: 'thumbnail',
      title: 'Vorschaubild (optional)',
      type: 'image',
      options: {hotspot: true},
      description: 'Kleines Bild in der Namensliste. Leer lassen, um einen Ausschnitt des Porträts zu verwenden.',
    }),
    defineField({
      name: 'artikel',
      title: 'Artikel',
      type: 'array',
      of: [{type: 'reference', to: [{type: 'artikel'}]}],
    }),
    defineField({
      name: 'personen',
      title: 'Verbundene Personen',
      type: 'array',
      of: [{type: 'reference', to: [{type: 'person'}]}],
    }),
    defineField({
      name: 'orte',
      title: 'Orte',
      type: 'array',
      of: [{type: 'reference', to: [{type: 'ort'}]}],
    }),
    defineField({
      name: 'weitereOrte',
      title: 'Weitere Orte (ohne Karteneintrag)',
      type: 'array',
      of: [{type: 'string'}],
      options: {layout: 'tags'},
      description: 'Orte, die (noch) keinen eigenen Eintrag haben. Erscheinen als Schlagwort ohne Link zur Karte.',
    }),
    defineField({
      name: 'reihenfolge',
      title: 'Reihenfolge',
      type: 'number',
      description: 'Position in der Namensliste (kleinere Zahl = weiter vorne). Leer = am Ende.',
    }),
  ],
  orderings: [{title: 'Reihenfolge', name: 'reihenfolge', by: [{field: 'reihenfolge', direction: 'asc'}]}],
  preview: {select: {title: 'name', subtitle: 'jahre', media: 'portrait'}},
})
