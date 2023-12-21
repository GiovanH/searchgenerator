#!/bin/python3
import ruamel.yaml
import sys
import random
import itertools
import functools

yaml = ruamel.yaml.YAML(typ='unsafe')
# yaml.default_flow_style = False

class PredicateBag():
    """A collection of predicates"""

    def __init__(self):
        super().__init__()
        self.narrowers = []

    def addNarrower(self, n):
        self.narrowers.append(n)

    def addRandom(self, ns):
        ours = set(self.narrowers)
        newopts = set(ns)
        try:
            choice = random.choice(list(newopts - ours))
            self.addNarrower(choice)
        except IndexError:
            raise IndexError("No new possibilities to add", ours, newopts)

    @property
    def all_predicate_sets(self):
        for n in self.narrowers:
            yield n.getPredicateOpts()

    def __repr__(self):
        return f"<{type(self).__name__} {[repr(n) for n in self.narrowers]}>"

    @functools.lru_cache()
    def formatJoin(self, predicate_list):
        expanded_predicate_list = list(predicate_list)
        for p in predicate_list:
            if isinstance(p, MultiAndPredicate):
                expanded_predicate_list.remove(p)
                expanded_predicate_list += p.all_predicates()

        return " ".join(
            p.format() for p in
            sorted(set(expanded_predicate_list), key=lambda t: type(t).__name__)
        )

    def formatRandom(self):
        permutation = [random.choice(predicates_set).format() for predicates_set in self.all_predicate_sets]
        return self.formatJoin(permutation)

    def formatAll(self):
        return [*map(self.formatJoin, [*itertools.product(*self.all_predicate_sets)])]

class Narrower():
    """A choice of topic to narrow a search to"""

    def to_input(self):
        return [
            opt.value
            if isinstance(opt, TagPredicate)
            else opt
            for opt in self.predicate_opts
        ]

    def __init__(self, name, predicateOpts=[]):
        super().__init__()
        self.name = name
        self.predicate_opts = []
        self.addPredicateOpts(predicateOpts)


    def __repr__(self):
        return f"<{type(self).__name__} {self.name!r}>"

    def addPredicateOpt(self, newpred):
        self.predicate_opts.append(newpred)

    def addPredicateOpts(self, newpreds):
        for np in newpreds:
            self.addPredicateOpt(np)

    def getPredicateOpts(self):
        yield from self.predicate_opts

class BasePredicate():
    """A condition, like a host, tag, or rating"""

    def __init__(self, value=None):
        super().__init__()
        self.value = value

    def all_predicates(self):
        yield self

    def format(self):
        return self.value

    def __repr__(self):
        return f"<{type(self).__name__} {self.format()}>"

class TagPredicate(BasePredicate):
    pass

class SitePredicate(BasePredicate):
    def format(self):
        return "SITE:" + self.value


class PredicateContainer(BasePredicate):
    def all_predicates(self):
        yield from (
            TagPredicate(tag)
            if isinstance(tag, str)
            else tag
            for tag in self.value
        )

class MultiAndPredicate(PredicateContainer):
    pass


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


def main():
    args = parse_args()

    with open(args.input, "r") as fp:
        request = yaml.load(fp)

        def _load(kind):
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
        k_fandom = _load('fandom')
        k_theme = _load('theme')

    with open("_resolved.yaml", "w") as fp:
        yaml.dump({
            "type": "resolved",
            "fandom": k_fandom,
            "theme": k_theme
        }, fp)
    with open("_resolved2.yaml", "w") as fp:
        yaml.dump({
            "fandom": {n.name: n.to_input() for n in k_fandom},
            "theme": {n.name: n.to_input() for n in k_theme}
        }, fp)

    for i in range(10):
        bag = PredicateBag()
        for narrowers in random.choice([
            (k_theme, k_theme), (k_theme, k_theme),
            (k_theme, k_fandom), (k_theme, k_fandom),
            (k_theme,),
            (k_fandom,),
        ]):
            bag.addRandom(narrowers)

        # print(repr(bag))
        # yaml.dump(bag, sys.stdout)
        # print()
        # print(bag.formatRandom())
        queries = bag.formatAll()
        random.shuffle(queries)
        print('\n'.join(queries[:5]))

    # yaml.dump(yaml.load(dumps(bag)), sys.stdout)




if __name__ == "__main__":
    main()
