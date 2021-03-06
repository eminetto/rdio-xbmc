import random
from collections import deque


class RdioRadio:

  _RETURN_TO_BASE_ARTIST_FREQUENCY = 5
  _NO_REPEAT_TRACK_COUNT = 25
  _NUM_TOP_TRACKS_TO_CHOOSE_FROM = 20
  _MAX_RELATED_ARTIST_DEPTH = 3

  _RADIO_STATE_FILE_NAME = 'rdio-radio-state.json'
  _INITIAL_STATE = {'played_tracks': deque()}

  def __init__(self, addon, rdio_api):
    self._addon = addon
    self._rdio_api = rdio_api
    self._state = addon.load_data(self._RADIO_STATE_FILE_NAME)
    if not self._state:
      self._state = self._INITIAL_STATE


  def next_track(self, base_artist, last_artist = None, user = None):
    if not last_artist:
      self._state = self._INITIAL_STATE

    track = None
    artist_blacklist = [base_artist, last_artist]
    use_base_artist = not last_artist or random.randint(1, self._RETURN_TO_BASE_ARTIST_FREQUENCY) == 1

    attempt_number = 0
    while not track:
      attempt_number = attempt_number + 1
      artist = base_artist if use_base_artist else self._choose_artist(base_artist, last_artist, user, artist_blacklist)
      if artist:
        track = self._choose_track(artist, user)
        if not track:
          artist_blacklist.append(artist)
      else:
        self._addon.log_debug("Didn't find an artist")
        if attempt_number == 1:
          self._addon.log_debug("Clearing blacklist")
          artist_blacklist = []
        elif attempt_number == 2:
          self._addon.log_debug("Clearing played tracks list")
          self._state['played_tracks'] = deque()
        else:
          self._addon.log_debug("Giving up")
          break

    if track:
      self._record_played_track(track['key'])

    self._save_state()
    return track


  def _choose_artist(self, base_artist, last_artist, user, artist_blacklist = None, depth = 1):
    self._addon.log_debug("Choosing artist with base artist %s and last artist %s" % (base_artist, last_artist))

    candidate_artist_keys = self._candidate_artists(base_artist, last_artist, user, artist_blacklist)
    if candidate_artist_keys:
      chosen_artist = random.choice(candidate_artist_keys)
    else:
      chosen_artist = None

    self._addon.log_debug("Chose artist: %s" % str(chosen_artist))
    return chosen_artist


  def _candidate_artists(self, base_artist, last_artist, user, artist_blacklist = None, artist_recurse_blacklist = None, depth = 1):
    self._addon.log_debug("Finding candidate artists with last artist %s" % last_artist)
    if artist_blacklist is None:
      artist_blacklist = []

    related_artist_keys = self._cached_value('related_artists_' + last_artist,
        lambda: [artist['key'] for artist in self._rdio_api.call('getRelatedArtists', artist = last_artist)])

    allowed_related_artist_keys = list(set(related_artist_keys) - set(artist_blacklist))

    if not user:
      self._addon.log_debug("Candidate artists: %s" % str(allowed_related_artist_keys))
      return allowed_related_artist_keys

    collection_artist_keys = self._cached_value('artists_in_collection_' + user,
      lambda: [artist['artistKey'] for artist in self._rdio_api.call('getArtistsInCollection', user = user)])

    self._addon.log_debug("Related artists: %s, collection artists: %s, blacklist: %s" % (str(allowed_related_artist_keys), str(collection_artist_keys), str(artist_blacklist)))
    candidate_artist_keys = list(set(allowed_related_artist_keys) & set(collection_artist_keys))
    self._addon.log_debug("Candidate artists: %s" % str(candidate_artist_keys))

    if not candidate_artist_keys and depth < self._MAX_RELATED_ARTIST_DEPTH:
      if artist_recurse_blacklist is None:
        artist_recurse_blacklist = []

      artist_recurse_blacklist.append(last_artist)

      recurse_artists = list(set(related_artist_keys) - set(artist_recurse_blacklist))
      self._addon.log_debug("Recursing related artists %s, recurse blacklist: %s" % (str(recurse_artists), str(artist_recurse_blacklist)))
      for related_artist in recurse_artists:
        candidate_artist_keys = self._candidate_artists(base_artist, related_artist, user, artist_blacklist, artist_recurse_blacklist, depth + 1)
        if candidate_artist_keys:
          break

    return candidate_artist_keys


  def _choose_track(self, artist, user):
    tracks = None
    if user:
      tracks = self._cached_value('artist_tracks_in_collection_%s_%s' % (artist, user), lambda: self._rdio_api.call('getTracksForArtistInCollection', artist = artist, user = user))
    else:
      tracks = self._cached_value('artist_tracks_%s' % artist, self._rdio_api.call('getTracksForArtist', artist = artist, extras = 'playCount,isInCollection', start = 0, count = self._NUM_TOP_TRACKS_TO_CHOOSE_FROM))

    chosen_track = None
    if tracks:
      played_tracks = self._state['played_tracks']
      candidate_tracks = [track for track in tracks if track['canStream'] and track['key'] not in played_tracks]
      if candidate_tracks:
        chosen_track = random.choice(candidate_tracks)

    return chosen_track


  def _save_state(self):
    self._addon.save_data(self._RADIO_STATE_FILE_NAME, self._state)


  def _cached_value(self, key, fn):
    value = None
    if key in self._state:
      value = self._state[key]
    else:
       value = fn()
       self._state[key] = value

    return value

  def _record_played_track(self, track_key):
    played_tracks = self._state['played_tracks']
    played_tracks.append(track_key)
    if len(played_tracks) > self._NO_REPEAT_TRACK_COUNT:
      played_tracks.popleft()
