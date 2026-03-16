from django.shortcuts import render
from django.views import generic
from series.models import Series, SeriesVisibility

# Create your views here.

class SeriesListView(generic.ListView):
    template_name = 'series/series_list.html'
    context_object_name = 'series_list'

    def get_queryset(self):
        return Series.objects.filter(visibility=SeriesVisibility.PUBLIC).order_by('-created_at').prefetch_related('genres').select_related('author')
