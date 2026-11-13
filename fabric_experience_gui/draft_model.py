from dataclasses import dataclass
from io import StringIO
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError
from xml.sax.saxutils import quoteattr


CONTROL_TYPES = frozenset({'sequential', 'parallel_any', 'parallel_all', 'recovery'})


@dataclass(frozen=True)
class DraftNode:
    path: tuple[int, ...]
    kind: str
    attributes: tuple[tuple[str, str], ...]
    children: tuple['DraftNode', ...] = ()


class DraftModel:
    def __init__(self, xml_text: str):
        try:
            document = minidom.parseString(xml_text)
        except (ExpatError, ValueError) as exc:
            raise ValueError(f'Invalid XML: {exc}') from exc
        if document.doctype is not None:
            raise ValueError('Document type declarations are not supported by the draft model.')
        root = document.documentElement
        if root.tagName != 'Plan' or root.namespaceURI:
            raise ValueError('Draft must have an unnamespaced Plan root.')
        self._document = document
        self._original = xml_text
        self._changed = False
        self.root = self._read_node(root, ())

    @classmethod
    def _read_node(cls, element, path):
        kind = element.tagName
        if element.namespaceURI or kind not in ('Plan', 'Control', 'Runner'):
            raise ValueError(f'Unsupported structural element: {kind}.')
        if kind == 'Control' and element.getAttribute('type') not in CONTROL_TYPES:
            raise ValueError(f'Unsupported Control type: {element.getAttribute("type") or "(missing)"}.')
        if kind == 'Runner':
            if not element.getAttribute('interface').strip() or not element.getAttribute('provider').strip():
                raise ValueError('Runner requires non-empty interface and provider attributes.')
            if any(child.nodeType == Node.ELEMENT_NODE or
                   (child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE) and child.data.strip())
                   for child in element.childNodes):
                raise ValueError('Runner child elements or text are not supported; Fabric reads runner attributes as parameters.')
            children = ()
        else:
            elements = []
            for child in element.childNodes:
                if child.nodeType == Node.ELEMENT_NODE:
                    if child.tagName == 'Plan':
                        raise ValueError('Nested Plan elements are not supported.')
                    elements.append(child)
                elif child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE) and child.data.strip():
                    raise ValueError(f'Text inside {kind} is not supported.')
            if not elements:
                raise ValueError(f'{kind} must contain at least one Control or Runner.')
            children = tuple(cls._read_node(child, path + (index,)) for index, child in enumerate(elements))
        attributes = tuple((element.attributes.item(index).name, element.attributes.item(index).value)
                           for index in range(element.attributes.length))
        return DraftNode(path, kind, attributes, children)

    def set_runner_pair(self, path, interface, provider, valid_pairs):
        if (interface, provider) not in valid_pairs:
            raise ValueError('Interface and provider are not a verified runnable pair.')
        element = self._document.documentElement
        node = self.root
        for index in path:
            if not isinstance(index, int) or index < 0 or index >= len(node.children):
                raise ValueError('Draft node path does not exist.')
            children = [child for child in element.childNodes if child.nodeType == Node.ELEMENT_NODE]
            node = node.children[index]
            element = children[index]
        if node.kind != 'Runner':
            raise ValueError('Draft node is not a Runner.')
        element.setAttribute('interface', interface)
        element.setAttribute('provider', provider)
        self._changed = True
        self.root = self._read_node(self._document.documentElement, ())

    def to_xml(self):
        if not self._changed:
            return self._original
        output = StringIO()
        version = self._document.version or '1.0'
        standalone = self._document.standalone
        declaration = f'<?xml version="{version}"'
        if standalone is not None:
            declaration += f' standalone="{"yes" if standalone else "no"}"'
        output.write(declaration + '?>')

        def write(node):
            if node.nodeType != Node.ELEMENT_NODE:
                node.writexml(output)
                return
            output.write(f'<{node.tagName}')
            for index in range(node.attributes.length):
                attribute = node.attributes.item(index)
                output.write(f' {attribute.name}={quoteattr(attribute.value)}')
            if not node.childNodes:
                output.write('/>')
                return
            output.write('>')
            for child in node.childNodes:
                write(child)
            output.write(f'</{node.tagName}>')

        for child in self._document.childNodes:
            write(child)
        return output.getvalue()