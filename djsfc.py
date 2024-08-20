import importlib

import django
from django import template


class Router:
    def __init__(self, name):
        self.name = name
        self.patterns = {}
        self.sub_routers = {}

    def __str__(self):
        return self.name

    def route(self, method, pattern):
        def decorator(view_func):
            view_name = view_func.__name__
            handlers = self.patterns.setdefault(pattern, {})
            if method in handlers:
                raise ValueError(f'Handler for {method} {pattern} already exists: {handlers[method]}')
            handlers[method] = (view_func, view_name)
            return view_func
        return decorator

    def route_all(self, pattern, sub_router, name=None):
        if isinstance(sub_router, str):
            sub_router = importlib.import_module(sub_router).router
        if pattern in self.sub_routers:
            raise ValueError(f'Sub-router for {pattern} already exists: {self.sub_routers[pattern]}')
        self.sub_routers[pattern] = (sub_router, name)

    @property
    def urls(self):
        urls = []

        for pattern, handlers in self.patterns.items():
            view_func = MethodDispatchView(handlers, router=self)
            # we need to include view_func multiple times to get multiple names
            for method, (_, name) in handlers.items():
                urls.append(django.urls.path(
                    pattern,
                    view_func,
                    name=name,
                ))

        for pattern, (sub_router, name) in self.sub_routers.items():
            sub_urls = sub_router.urls
            urls.append(django.urls.path(
                pattern,
                django.urls.include((sub_urls, name), namespace=name),
            ))

        return tuple(urls)

    def get_relative_name(self, router):
        """
        Return namespace path from this router to the given router
        as a tuple of strings. Return None if the given router is not
        a sub-router of this router.
        """
        if self == router:
            return ()
        for pattern, (sub_router, name) in self.sub_routers.items():
            relative_name = sub_router.get_relative_name(router)
            if relative_name is not None:
                if name is None:
                    return relative_name
                else:
                    return (name,) + relative_name
        return None

    def reverse(self, request, view_name, *args, **kwargs):
        full_view_name = self.get_full_view_name(request, view_name)
        return django.urls.reverse(full_view_name, args=args, kwargs=kwargs)

    def get_full_view_name(self, request, view_name):
        assert view_name.startswith(':')
        name_path = request.router.get_relative_name(self)
        if name_path is None:
            raise ValueError(
                f'Cannot reverse URL {view_name} in router {self}. '
                f'Router {self} is not a sub-router of main matched router {request.router}.'
            )
        root_namespace = request.resolver_match.namespace
        if root_namespace:
            name_path = (root_namespace,) + name_path
        return ':'.join([
            *name_path,
            view_name[1:],
        ])


class MethodDispatchView:
    def __init__(self, handlers, router):
        self.handlers = handlers
        self.router = router

    def __call__(self, request, *args, **kwargs):
        handler = self.handlers.get(request.method)
        if handler is None:
            return django.http.HttpResponseNotAllowed(self.handlers.keys())
        view_func, _ = handler
        request.router = self.router
        return view_func(request, *args, **kwargs)


def parse_template(template_str, router):
    django_engine = django.template.engines['django']
    origin = django.template.Origin(router.name)
    origin.router = router
    template = django.template.Template(
        template_str,
        engine=django_engine.engine,
        origin=origin,
    )
    return django.template.backends.django.Template(
        template,
        django_engine,
    )


register = template.Library()


class AddNamespaceFilterExpression:
    def __init__(self, filter_expression, router):
        self.filter_expression = filter_expression
        self.router = router

    def resolve(self, context):
        resolved = self.filter_expression.resolve(context)
        if resolved.startswith(':'):
            resolved = self.router.get_full_view_name(context.request, resolved)
        return resolved


@register.tag
def url(parser, token):
    node = django.template.defaulttags.url(parser, token)
    if hasattr(parser.origin, 'router'):
        node.view_name = AddNamespaceFilterExpression(node.view_name, parser.origin.router)
    return node


def get_template_block(template, block_name):
    assert isinstance(template, django.template.backends.django.Template)
    node = get_block_from_nodelist(template.template.nodelist, block_name)
    if not node:
        raise ValueError(f'Block {block_name} not found in template')
    nodelist = node.nodelist
    source = template.template.source
    return django.template.backends.django.Template(PartialTemplate(
        nodelist,
        engine=template.backend.engine,
        origin=template.origin,
        source=source,
    ), template.backend)


class PartialTemplate(django.template.base.Template):
    def __init__(self, nodelist, engine, origin=None, source=None):
        self.nodelist = nodelist
        self.engine = engine
        self.origin = origin
        self.source = source
        self.name = None


def get_block_from_nodelist(nodelist, block_name):
    for node in nodelist:
        if isinstance(node, django.template.loader_tags.BlockNode) and node.name == block_name:
            return node
        for child_nodelist_name in getattr(node, 'child_nodelists', []):
            ret = get_block_from_nodelist(getattr(
                node, child_nodelist_name,
                [],  # RegroupNode and IncludeNode has no nodelist, but it has it registered in child_nodelists
            ), block_name)
            if ret is not None:
                return ret
    return None


class UnionTemplate:
    def __init__(self, templates):
        self.templates = templates

    def render(self, *args, **kwargs):
        return ''.join(template.render(*args, **kwargs) for template in self.templates)


class TemplateLoader:
    def __init__(self, engine):
        self.engine = engine

    def get_template(self, template_name, skip=None):
        assert skip is None
        template_name = template_name.replace('/', '.')
        module_name, variable_name = template_name.rsplit('.', 1)
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            raise django.template.exceptions.TemplateDoesNotExist(template_name)
        if not hasattr(module, variable_name):
            raise django.template.exceptions.TemplateDoesNotExist(template_name)
        template = getattr(module, variable_name)
        assert isinstance(template, django.template.backends.django.Template)
        return template.template

    def reset(self):
        pass
