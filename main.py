#!/bin/python3
import ruamel.yaml
import random
import itertools
import functools
import sys
import typing
from urllib.parse import urlencode, quote_plus, quote

yaml = ruamel.yaml.YAML(typ='unsafe')

debug_output = False


class BasePredicate():
    """A condition, like a host, tag, or rating"""

    VT: typing.TypeAlias = str  # typing.TypeVar('VT')

    def __init__(self, value: VT) -> None:
        super().__init__()
        self.value: BasePredicate.VT = value

    def all_predicates(self) -> 'typing.Iterable[BasePredicate]':
        yield self

    def format(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.format()}>"


Predicates: typing.TypeAlias = typing.Iterable[BasePredicate]
PredicateOrTagstr: typing.TypeAlias = typing.Union[BasePredicate, str]


class TagPredicate(BasePredicate):
    def formatBinOp(self, taglist, op):
        if op == "AND":
            return " ".join(
                p.format() for p in
                [self, *taglist]
            )
        else:
            raise ValueError(op)


class TagPredicateAO3(BasePredicate):
    key = 'tag'

    def format(self) -> str:
        return f'{self.key}:"{self.value}"'

    def formatBinOp(self, taglist, op):
        return '(' + f" {op} ".join(
            p.format() for p in
            [self, *taglist]
        ) + ")"


class NotPredicateAO3(TagPredicateAO3):
    def format(self) -> str:
        return f'NOT {super().format()}'


class KVPredicateAO3(TagPredicateAO3):
    def __init__(self, value, key) -> None:
        self.key: str = key
        self.value: BasePredicate.VT = value



class SitePredicate(TagPredicate):
    def format(self):
        return "SITE:" + self.value


class PredicateContainer(BasePredicate):
    def __init__(self, value: typing.Iterable[PredicateOrTagstr], default_constructor) -> None:
        super().__init__(value)  # type: ignore[arg-type]
        self.default_constructor: typing.Callable[[str], BasePredicate] = default_constructor

    def all_predicates(self) -> Predicates:
        yield from (
            self.default_constructor(tag)
            if isinstance(tag, str)
            else tag
            for tag in self.value
        )


class MultiAndPredicate(PredicateContainer):
    op = 'AND'

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.value!r}>"

    def format(self):
        taglist = [*self.all_predicates()]
        fallthrough = [*self.all_predicates()][0]

        if len(taglist) > 1:
            # print(self.__class__.__name__, 'format', fallthrough.__class__, taglist)
            first, *tail = taglist
            res = fallthrough.__class__.formatBinOp(first, tail, self.op)
            # print(self.__class__.__name__, 'format resolved', repr(res))
            return res
        else:
            return taglist[0].format()

    def formatBinOp(self, taglist, op):
        fallthrough = [*self.all_predicates()][0]

        if len(taglist) > 0:
            # print(self.__class__.__name__, 'formatBinOp fallthrough', op, fallthrough.__class__, taglist)
            res = fallthrough.__class__.formatBinOp(self, taglist, op)
            # print(self.__class__.__name__, 'formatBinOp resolved', repr(res))
            return res
        else:
            # print(self.__class__.__name__, 'formatBinOp lone', taglist[0])
            return self.format()


class MultiOrPredicate(MultiAndPredicate):
    op = 'OR'


class Narrower():
    """A choice of topic to narrow a search to"""

    def to_input(self) -> typing.Iterable[PredicateOrTagstr]:
        return [
            opt.value
            if isinstance(opt, TagPredicate)
            else opt
            for opt in self.predicate_opts
        ]

    def __init__(self, name: str, predicate_opts: Predicates) -> None:
        super().__init__()
        self.name: str = name
        self.predicate_opts: list[BasePredicate] = []
        self.addPredicateOpts(predicate_opts)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r}>"

    def addPredicateOpt(self, newpred: BasePredicate) -> None:
        if not isinstance(newpred, BasePredicate):
            raise TypeError(newpred)
        self.predicate_opts.append(newpred)

    def addPredicateOpts(self, newpreds: Predicates) -> None:
        for np in newpreds:
            self.addPredicateOpt(np)

    def getPredicateOpts(self) -> Predicates:
        yield from self.predicate_opts


class PredicateBag():
    """A collection of predicates"""
    default_constructor: typing.Type[BasePredicate] = TagPredicate

    def __init__(self) -> None:
        super().__init__()
        self.narrowers: list[Narrower] = []

    def addNarrower(self, n: Narrower) -> None:
        self.narrowers.append(n)

    def addRandom(self, ns: typing.Iterable[Narrower]) -> None:
        ours: set[Narrower] = set(self.narrowers)
        newopts: set[Narrower] = set(ns)
        try:
            choice = random.choice(list(newopts - ours))
            self.addNarrower(choice)
        except IndexError as e:
            raise IndexError("No new possibilities to add", ours, newopts) from e

    @property
    def all_predicate_sets(self) -> typing.Iterable[Predicates]:
        for n in self.narrowers:
            yield n.getPredicateOpts()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {[repr(n) for n in self.narrowers]}>"

    def formatRandom(self) -> str:
        permutation = [
            random.choice([*predicates_set]).format()
            for predicates_set
            in self.all_predicate_sets
        ]
        return MultiAndPredicate(permutation, self.default_constructor).format()

    def formatAll(self) -> typing.Iterable[str]:
        return [
            MultiAndPredicate(andlist, self.default_constructor).format()
            for andlist in
            itertools.product(*self.all_predicate_sets)
        ]


class PredicateBagAO3(PredicateBag):
    default_constructor: typing.Type[BasePredicate] = TagPredicateAO3

    def formatAll(self) -> typing.Iterable[str]:
        andlist: list[MultiOrPredicate] = [
            MultiOrPredicate([*n.getPredicateOpts()], self.default_constructor)
            for n in self.narrowers
        ]
        return [
            MultiAndPredicate(andlist, self.default_constructor).format()[1:-1]
        ]

def dumps(obj):
    from io import StringIO
    with StringIO() as sp:
        yaml.dump(obj, sp)
        return sp.getvalue()


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="()",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--input", "-i", default="input.yaml")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(args.input, "r") as fp:
        request = yaml.load(fp)

        def _load(kind) -> typing.Iterable[Narrower]:
            if not isinstance(request[kind], dict):
                return

            if request.get("type") == "resolved":
                return request[kind]
            return [
                Narrower(key, [
                    request['default_predicate'](tag)
                    if isinstance(tag, str)
                    else tag
                    for tag in taglist
                ])
                for key, taglist in request[kind].items()
            ]

        input_categories = {
            k: _load(k)
            for k in request.keys()
        }

        bag_kind = request['bag_kind']
        patterns = request['patterns']
        default_predicate = request['default_predicate']

    with open("_resolved.yaml", "w") as fp:
        yaml.dump({
            "type": "resolved",
            **input_categories
        }, fp)
    with open("_resolved2.yaml", "w") as fp:
        yaml.dump({
            "fandom": {n.name: n.to_input() for n in input_categories['fandom']},
            "theme": {n.name: n.to_input() for n in input_categories['theme']}
        }, fp)

    with open("highlight.css", 'w') as fp:
        for catname, catlist in input_categories.items():
            color = {
                'fandom': 'yellow',
                'theme': 'lightblue'
            }.get(catname, 'blue')
            if isinstance(catlist, list):
                for narrower in catlist:
                    queries = [
                        # quote(tag.value)
                        tag.value.replace(' ', '%20')
                        for tag in
                        narrower.getPredicateOpts()
                    ]
                    if len(queries) > 0:
                        selector = ', '.join(f'[href^="/tags/{query}"]' for query in queries)
                        fp.write(f"{selector} {{ background: {color}; }}\n")

    for i in range(10):
        # bag = bag_kind()

        selected_narrowers = set([None])

        def _readLevel(op, children):
            nonlocal selected_narrowers

            child_items = []
            for child in children:
                if isinstance(child, dict):
                    for ck, cv in child.items():
                        child_items.append(_readLevel(ck, cv))
                elif isinstance(child, str):
                    # narrower: typing.Optional[Narrower] = None
                    # while narrower in selected_narrowers:
                    narrower = random.choice([*set(input_categories[child]) - selected_narrowers])
                    # print(narrower, selected_narrowers, child)
                    if not narrower.name.startswith('_'):
                        print(op, narrower)
                    predicate_opts = [*narrower.getPredicateOpts()]
                    if len(predicate_opts) > 0:
                        selected_narrowers.add(narrower)
                        try:
                            or_predicate = MultiOrPredicate(predicate_opts, default_predicate)
                            or_predicate.format()  # verify this doesn't error
                            child_items.append(
                                # narrower
                                or_predicate
                            )
                        except ValueError:
                            child_items.append(random.choice(predicate_opts))
                else:
                    raise NotImplementedError(child.__class__)
            if op == 'AND':
                return MultiAndPredicate(child_items, default_predicate)
            elif op == 'OR':
                return MultiOrPredicate(child_items, default_predicate)
            else:
                raise NotImplementedError(op)

        for k, v in random.choice(patterns).items():
            search = _readLevel(k, v).format()

            if debug_output:
                print(repr(search))
                yaml.dump(search, sys.stdout)
                print()

            print(search)

            if bag_kind == PredicateBagAO3:
                query = quote_plus(search)
                print(f"https://archiveofourown.org/works/search?work_search%5Bquery%5D={query}\n")

            # while k:
            #     print(k, v)
            #     if k == 'AND':
            #         pass
            #     elif k == 'OR':
            #         pass
            #     else:
            #         k = None

            # bag.addRandom(input_categories[pattern])

        # for narrowers in random.choice([
        #     (k_theme, k_theme), (k_theme, k_theme),
        #     (k_theme, k_fandom), (k_theme, k_fandom),
        #     # (k_theme,),
        #     # (k_fandom,),
        # ]):
        #     bag.addRandom(narrowers)

        # if debug_output:
        #     print(repr(bag))
        #     yaml.dump(bag, sys.stdout)
        #     print()
            # print(bag.formatRandom())

        # queries: list[str] = [*bag.formatAll()]
        # random.shuffle(queries)
        # print('\n'.join(queries[:5]))

    # yaml.dump(yaml.load(dumps(bag)), sys.stdout)


if __name__ == "__main__":
    main()
